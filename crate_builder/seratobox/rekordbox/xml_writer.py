"""Write the Rekordbox XML import format (`DJ_PLAYLISTS`).

    DJ_PLAYLISTS Version="1.0.0"
      PRODUCT
      COLLECTION Entries
        TRACK TrackID Name Artist ... Location="file://localhost/<percent-encoded path>"
          TEMPO Inizio Bpm Metro Battito
          POSITION_MARK Name Type Start [End] Num [Red Green Blue]
      PLAYLISTS
        NODE Type="0" Name="ROOT" Count
          NODE Type="0" (folder) Name Count
          NODE Type="1" (playlist) Name KeyType="0" Entries
            TRACK Key=<TrackID>

POSITION_MARK: Type 0 = cue, 4 = loop (with End). Num 0..7 = hot cue A..H,
Num -1 = memory cue/loop. Positions are seconds with millisecond precision.
"""

from __future__ import annotations

import os
import re
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from urllib.parse import quote

from .. import __version__

MARK_CUE = 0
MARK_LOOP = 4
MEMORY_NUM = -1
HOT_CUE_SLOTS = 8

_INVALID_XML_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


@dataclass
class RbMark:
    start_s: float
    num: int  # 0..7 hot cue, -1 memory
    type: int = MARK_CUE
    end_s: float | None = None
    name: str = ""
    rgb: tuple[int, int, int] | None = None


@dataclass
class RbTempo:
    inizio_s: float
    bpm: float
    metro: str = "4/4"
    battito: int = 1


@dataclass
class RbTrack:
    track_id: int
    path: Path
    name: str
    artist: str = ""
    album: str = ""
    genre: str = ""
    kind: str = ""
    size: int | None = None
    total_time_s: float | None = None
    average_bpm: float | None = None
    date_added: str = ""
    bit_rate: int | None = None
    sample_rate: int | None = None
    comments: str = ""
    tonality: str = ""
    tempos: list[RbTempo] = field(default_factory=list)
    marks: list[RbMark] = field(default_factory=list)


@dataclass
class RbNode:
    """A playlist tree node: a folder if `children` is not None, else a playlist."""

    name: str
    children: list[RbNode] | None = None
    track_ids: list[int] = field(default_factory=list)


def location_uri(path: PurePath) -> str:
    """`file://localhost/` + the absolute path, UTF-8 percent-encoded.

    macOS: `file://localhost/Users/...`. Windows keeps the drive letter
    unencoded, as Rekordbox writes it: `file://localhost/C:/Users/...`.
    """
    posix = path.as_posix()
    drive = re.match(r"^([A-Za-z]:)(/.*)?$", posix)
    if drive:
        return "file://localhost/" + drive.group(1) + quote(drive.group(2) or "/", safe="/")
    if not posix.startswith("/"):
        posix = "/" + posix
    return "file://localhost" + quote(posix, safe="/")


def clean_text(text: str | None) -> str:
    return _INVALID_XML_CHARS.sub("", text or "")


def seconds(value: float) -> str:
    return f"{value:.3f}"


def build_tree(tracks: list[RbTrack], root_children: list[RbNode]) -> ET.ElementTree[ET.Element]:
    root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
    ET.SubElement(root, "PRODUCT", Name="Crate Builder", Version=__version__, Company="Crate Builder")
    collection = ET.SubElement(root, "COLLECTION", Entries=str(len(tracks)))
    for track in tracks:
        collection.append(_track_element(track))
    playlists = ET.SubElement(root, "PLAYLISTS")
    playlists.append(_node_element(RbNode("ROOT", children=root_children)))
    ET.indent(root, space="  ")
    return ET.ElementTree(root)


def write_xml(tracks: list[RbTrack], root_children: list[RbNode], output: Path) -> None:
    """Write atomically: a temp file in the same folder, then rename over `output`."""
    tree = build_tree(tracks, root_children)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".seratobox-", suffix=".xml", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            tree.write(fh, encoding="UTF-8", xml_declaration=True)
            fh.write(b"\n")
        os.replace(tmp, output)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _track_element(t: RbTrack) -> ET.Element:
    attrs = {
        "TrackID": str(t.track_id),
        "Name": clean_text(t.name),
        "Artist": clean_text(t.artist),
        "Album": clean_text(t.album),
        "Genre": clean_text(t.genre),
        "Kind": t.kind,
        "Size": str(t.size) if t.size is not None else "",
        "TotalTime": str(round(t.total_time_s)) if t.total_time_s else "",
        "AverageBpm": f"{t.average_bpm:.2f}" if t.average_bpm else "",
        "DateAdded": t.date_added,
        "BitRate": str(t.bit_rate) if t.bit_rate else "",
        "SampleRate": str(t.sample_rate) if t.sample_rate else "",
        "Comments": clean_text(t.comments),
        "Tonality": clean_text(t.tonality),
        "Location": location_uri(t.path),
    }
    el = ET.Element("TRACK", {k: v for k, v in attrs.items() if v != ""})
    for tempo in t.tempos:
        ET.SubElement(
            el,
            "TEMPO",
            Inizio=seconds(tempo.inizio_s),
            Bpm=f"{tempo.bpm:.2f}",
            Metro=tempo.metro,
            Battito=str(tempo.battito),
        )
    for mark in t.marks:
        m = {"Name": clean_text(mark.name), "Type": str(mark.type), "Start": seconds(mark.start_s)}
        if mark.end_s is not None:
            m["End"] = seconds(mark.end_s)
        m["Num"] = str(mark.num)
        if mark.rgb is not None:
            m["Red"], m["Green"], m["Blue"] = (str(c) for c in mark.rgb)
        ET.SubElement(el, "POSITION_MARK", m)
    return el


def _node_element(node: RbNode) -> ET.Element:
    if node.children is not None:
        el = ET.Element("NODE", Type="0", Name=clean_text(node.name), Count=str(len(node.children)))
        for child in node.children:
            el.append(_node_element(child))
        return el
    el = ET.Element(
        "NODE",
        Name=clean_text(node.name),
        Type="1",
        KeyType="0",
        Entries=str(len(node.track_ids)),
    )
    for track_id in node.track_ids:
        ET.SubElement(el, "TRACK", Key=str(track_id))
    return el
