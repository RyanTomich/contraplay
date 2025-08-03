import csv
from itertools import islice
from dataclasses import dataclass
from collections import defaultdict, Counter
import matplotlib.pyplot as plt
import numpy as np
from urllib.parse import urlparse
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os
from dotenv import load_dotenv
from matplotlib_venn import venn2
from difflib import SequenceMatcher
from wordcloud import WordCloud
import lyricsgenius
import time
import re
from pathlib import Path


forbidden_words = {'remastered', 'remaster', 'chorus', 'verse', '',
    "the","a","an","and","or","but","if","so","for","to","of","at","by",
    "in","on","with","from","up","down","out","over","under","again","once",
    "is","am","are","was","were","be","been","being","have","has","had",
    "do","does","did","will","would","shall","should","can","could","may",
    "might","must", "uh","um","er","ah","oh","like","yeah","yep","okay","ok","really",
    "just","very","literally","actually","basically","kinda","sorta", 'la'
}

@dataclass(frozen=True, slots=True)
class Song:
    title: str
    artist: str
    album: str
    duration: int # seconds

    @classmethod
    def create(cls, title: str, artist: str, album: str, duration:str| int) -> "Song":
        return cls(title, artist, album, cls._parse_duration(duration))

    @classmethod
    def _parse_duration(cls, raw: str | int) -> int:
        if isinstance(raw, int):
            return raw
        minutes, seconds = raw.split(":")
        return int(minutes) * 60 + int(seconds)

    def __str__(self) -> str:
        return f"{self.title[:40]:<40} | {self.artist[:20]:<20} | {self.album[:25]:<25} | {self.duration:>5}s"

    def __eq__(self, that):
        """Returns true if songs are effectively equal. Intentionally week to account for title variants of the same song.
        """
        a = self.title.lower()
        b = that.title.lower()
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.8

        # title_match = self.title == that.title
        # artist_match = self.artist == that.artist
        # album_match = self.album == that.album

        # title_match = similar(self.title, that.title)
        # artist_match = similar(self.artist, that.artist)
        # album_match = similar(self.album, that.album)

class Playlist():
    def __init__(self, songs:list[Song], tag:str = ''):
        self.songs = songs
        self.tag=None

    def __iter__(self):
        for i in self.songs:
            yield i

    def __len__(self):
        return len(self.songs)

    def duration_box(self):
        durations = [s.duration for s in self.songs]
        fig, ax = plt.subplots(figsize=(5,5))
        ax.boxplot(durations, vert=True)
        jitter = np.random.normal(1, 0.02, size=len(durations))
        ax.scatter(jitter, durations, alpha=0.2, color='blue', s=4, label='Individual Songs')

        ax.set_title(f'{self.tag} Song Duration Distribution')
        ax.set_ylabel('Duration (seconds)')
        ax.yaxis.grid(True)

        fig.tight_layout()
        fig.savefig(f'{self.tag}_duration_box.png', dpi=300)
        plt.close(fig)

    def artist_frequency_dist(self, freq = False):
        songs_by_artist = defaultdict(list)
        for s in self.songs:
            songs_by_artist[s.artist].append(s)

        assert sum(len(j) for i,j in songs_by_artist.items()) == len(self.songs)

        counts = {artist: len(lst) for artist, lst in songs_by_artist.items()}
        artists_sorted = sorted(counts, key=counts.get)

        if freq:
            out_path = 'artist_frequency_bar.png'
            fig, ax = plt.subplots(figsize=(20, 10))
            freqs_sorted   = [counts[a] for a in artists_sorted]
            ax.bar(artists_sorted, freqs_sorted)
            ax.set_ylabel("Number of songs")
            ax.set_xlabel("Artist")
            ax.set_title(f"{self.tag} Songs per artist (ascending)")
            ax.set_xticklabels(artists_sorted, rotation=45, ha="right", fontsize=6)

        else:
            out_path = 'artist_frequency_dist.png'
            fig, ax = plt.subplots(figsize=(5,5))
            freq_of_freq = Counter(counts.values())
            x, y = zip(*sorted(freq_of_freq.items()))
            ax.bar(x, y)
            ax.set_xlabel("Songs per artist")
            ax.set_ylabel("Number of artists")
            ax.set_title(f"{self.tag} Distribution of artist frequencies")

        ax.yaxis.grid(True)
        fig.tight_layout()
        fig.savefig(f'{self.tag}_' + out_path, dpi=300)
        plt.close(fig)


    def print_all(self):
        for s in self.songs:
            print (s)


def parse_filepath(file_path:str) -> Playlist:
    songs = []
    with open(file_path, newline="", encoding="utf-8") as f:
        while True:
            song_chunk = list(islice(f, 5))
            if not song_chunk:
                break
            song_chunk = [line.strip() for line in song_chunk if line.strip()]

            if len(song_chunk) != 5:
                raise ValueError(f"Malformed entry: {song_chunk}")

            track_no, title, artist, album, duration = song_chunk
            songs.append(Song.create(title, artist, album, duration))
    return Playlist(songs)

def parse_spotify_url(playlist_url:str, tag='') -> Playlist:
    assert 'https://open.spotify.com/playlist' in playlist_url, f'{playlist_url} is not a spotify playlist link'
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        )
    )

    songs = []

    offset = 0
    while True:
        page = sp.playlist_items(
            playlist_url,
            offset=offset,
            limit=100,
            additional_types=["track"],  # ignore podcasts
        )
        for item in page["items"]:
            t = item["track"]
            songs.append(
                Song.create(
                    t["name"],
                    ", ".join(a["name"] for a in t["artists"]),
                    t["album"]["name"],
                    int(t["duration_ms"]/1000)
                )
            )
        offset += len(page["items"])
        if offset >= page["total"]:
            break

    return Playlist(songs, tag=tag)

def playlist_intersection(playlist_1: Playlist, playlist_2: Playlist) -> Playlist:
    song_intersection = []
    for s1 in playlist_1:
        for s2 in playlist_2:
            if s1 == s2:
                song_intersection.append(s1)

    return Playlist(song_intersection, tag='intersect')


def visualize_intersection_venn(len_s1:int, len_s2:int, len_intersection:int) -> None:
    only_s1 = len_s1 - len_intersection
    only_s2 = len_s2 - len_intersection
    venn2(subsets=(only_s1, only_s2, len_intersection), set_labels=('ryan', 'rachel'))
    plt.title("Playlist Intersection")
    plt.savefig("playlist_intersection_venn.png", dpi=300)
    plt.savefig('intersect.png', dpi=300)

def _sanitize(text: str) -> str:
    """Make an OS-safe, case-insensitive slug."""
    _filename_rx = re.compile(r"[^-\w\s]")
    return _filename_rx.sub("", text).strip().replace(" ", "_").lower()

def get_lyrics(song: Song, genius: lyricsgenius) -> str:
    folder = Path("lyrics_cache")
    folder.mkdir(exist_ok=True)
    fname = f"{_sanitize(song.artist)}-{_sanitize(song.title)}.txt"
    cache_path = folder / fname

    if cache_path.exists():
        print(f'{song} in cache')
        return cache_path.read_text(encoding="utf-8")
    try:
        result = genius.search_song(title=song.title, artist=song.artist, get_full_info=False)
        time.sleep(15)
        if result:
            cache_path.write_text(result.lyrics, encoding="utf-8")
            return result.lyrics
    except Exception as e:
        print(f"Error fetching lyrics for {song}: {e}")
    return ""

def wordCloud(playlist: Playlist, genius:lyricsgenius) -> None:
    text = ''
    for i in playlist:
        lyrics = get_lyrics(i, genius)
        words = lyrics.split()
        for w in words:
            # w = w.strip().lower()
            w = re.sub(r"[^\w]", "", w).lower()
            if w not in forbidden_words:
                text += f' { w}'

    wc = WordCloud(width=800, height=400, background_color='white').generate(text)

    plt.figure(figsize=(10, 5))
    plt.imshow(wc, interpolation='bilinear')
    plt.axis('off')
    plt.savefig(f'{playlist.tag}_wordCloud.png', dpi=300)

if __name__ == "__main__":
    pass
    load_dotenv()

    classics_playlist_url = 'https://open.spotify.com/playlist/0mxwuRxFnP7cedz2iWtdgE?si=98bdcca0d5cb4357'
    ryan_playlist = parse_spotify_url(classics_playlist_url, tag='Ryan')

    # ryan_playlist.artist_frequency_dist()
    # ryan_playlist.artist_frequency_dist(freq=True)
    # ryan_playlist.duration_box()

    genius = lyricsgenius.Genius(os.getenv("GENIUS_ACCESS_TOKEN"))
    wordCloud(ryan_playlist, genius)
