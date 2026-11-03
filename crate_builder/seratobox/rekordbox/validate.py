"""Structural checks against the Rekordbox XML import format.

Rekordbox publishes no XSD, so this encodes the documented format: the element
hierarchy, required attributes, attribute value types, and cross-references
between playlist entries and collection tracks. Returns a list of problems.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

_TRACK_REQUIRED = ("TrackID", "Name", "Location")
_MARK_TYPES = {"0", "1", "2", "3", "4"}


def validate_file(path: Path) -> list[str]:
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        return [f"not well-formed XML: {exc}"]
    return validate_tree(tree.getroot())


def validate_tree(root: ET.Element) -> list[str]:
    errors: list[str] = []
    if root.tag != "DJ_PLAYLISTS":
        return [f"root element is {root.tag}, expected DJ_PLAYLISTS"]
    if not root.get("Version"):
        errors.append("DJ_PLAYLISTS missing Version")
    if root.find("PRODUCT") is None:
        errors.append("missing PRODUCT")
    collection = root.find("COLLECTION")
    if collection is None:
        return [*errors, "missing COLLECTION"]
    tracks = collection.findall("TRACK")
    if collection.get("Entries") != str(len(tracks)):
        errors.append(f"COLLECTION Entries={collection.get('Entries')} but has {len(tracks)}")
    ids: set[str] = set()
    for track in tracks:
        errors.extend(_check_track(track, ids))
    playlists = root.find("PLAYLISTS")
    if playlists is None:
        return [*errors, "missing PLAYLISTS"]
    nodes = playlists.findall("NODE")
    if len(nodes) != 1 or nodes[0].get("Name") != "ROOT" or nodes[0].get("Type") != "0":
        errors.append("PLAYLISTS must contain exactly one folder NODE named ROOT")
    for node in nodes:
        errors.extend(_check_node(node, ids, "ROOT"))
    return errors


def _check_track(track: ET.Element, ids: set[str]) -> list[str]:
    errors: list[str] = []
    tid = track.get("TrackID", "?")
    for attr in _TRACK_REQUIRED:
        if track.get(attr) is None:
            errors.append(f"TRACK {tid} missing {attr}")
    if tid in ids:
        errors.append(f"duplicate TrackID {tid}")
    ids.add(tid)
    location = track.get("Location", "")
    if not location.startswith("file://localhost/"):
        errors.append(f"TRACK {tid} Location must start with file://localhost/")
    if any(ch in location for ch in " #?") or not location.isascii():
        errors.append(f"TRACK {tid} Location is not percent-encoded: {location!r}")
    for tempo in track.findall("TEMPO"):
        for attr in ("Inizio", "Bpm", "Metro", "Battito"):
            if tempo.get(attr) is None:
                errors.append(f"TRACK {tid} TEMPO missing {attr}")
        if not _is_float(tempo.get("Inizio"), minimum=0) or not _is_float(tempo.get("Bpm"), 1):
            errors.append(f"TRACK {tid} TEMPO has invalid Inizio/Bpm")
    hot_slots: set[str] = set()
    for mark in track.findall("POSITION_MARK"):
        mtype, num = mark.get("Type"), mark.get("Num")
        if mtype not in _MARK_TYPES:
            errors.append(f"TRACK {tid} POSITION_MARK has invalid Type {mtype}")
        if not _is_float(mark.get("Start"), minimum=0):
            errors.append(f"TRACK {tid} POSITION_MARK has invalid Start {mark.get('Start')}")
        if num is None or not num.lstrip("-").isdigit() or not -1 <= int(num) <= 7:
            errors.append(f"TRACK {tid} POSITION_MARK has invalid Num {num}")
        elif num != "-1":
            if num in hot_slots:
                errors.append(f"TRACK {tid} has two hot cues in slot {num}")
            hot_slots.add(num)
        if mtype == "4":
            end = mark.get("End")
            start = mark.get("Start")
            if not _is_float(end) or (_is_float(start) and float(end or 0) <= float(start or 0)):
                errors.append(f"TRACK {tid} loop has invalid End {end}")
        for attr in ("Red", "Green", "Blue"):
            value = mark.get(attr)
            if value is not None and not (value.isdigit() and 0 <= int(value) <= 255):
                errors.append(f"TRACK {tid} POSITION_MARK {attr}={value} out of range")
    return errors


def _check_node(node: ET.Element, ids: set[str], where: str) -> list[str]:
    errors: list[str] = []
    ntype = node.get("Type")
    name = node.get("Name")
    here = f"{where}/{name}" if where != name else where
    if name is None:
        errors.append(f"NODE under {where} missing Name")
    if ntype == "0":
        children = node.findall("NODE")
        if node.get("Count") != str(len(children)):
            errors.append(f"folder {here} Count={node.get('Count')} but has {len(children)}")
        if node.findall("TRACK"):
            errors.append(f"folder {here} contains TRACK entries")
        for child in children:
            errors.extend(_check_node(child, ids, here))
    elif ntype == "1":
        entries = node.findall("TRACK")
        if node.get("Entries") != str(len(entries)):
            errors.append(f"playlist {here} Entries={node.get('Entries')} but has {len(entries)}")
        if node.get("KeyType") != "0":
            errors.append(f"playlist {here} KeyType must be 0 (TrackID keys)")
        for entry in entries:
            if entry.get("Key") not in ids:
                errors.append(f"playlist {here} references unknown TrackID {entry.get('Key')}")
    else:
        errors.append(f"NODE {here} has invalid Type {ntype}")
    return errors


def _is_float(value: str | None, minimum: float | None = None) -> bool:
    if value is None:
        return False
    try:
        number = float(value)
    except ValueError:
        return False
    return minimum is None or number >= minimum
