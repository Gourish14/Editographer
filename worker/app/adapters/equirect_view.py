"""Rectilinear views of an equirectangular frame, as pure numpy geometry.

Spec: specs/08-osmo360.md (rule 5: SAM 2 follows the subject on a view centered on it)

Yaw grows to the right, pitch grows upward, the same as the camera path. A subject cut in two by
the frame edge is whole in a view centered on it, and the view has no equirect stretch.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

MAX_VIEW_PITCH = 80.0


def view_rays(us: Any, vs: Any, size: int, fov: float, yaw: float, pitch: float) -> tuple[Any, Any]:
    """Longitude and latitude in degrees of view pixels (`us`, `vs`) of a square view."""
    focal = (size / 2) / math.tan(math.radians(fov) / 2)
    x = (np.asarray(us, dtype=np.float64) - size / 2) / focal
    y = -(np.asarray(vs, dtype=np.float64) - size / 2) / focal
    z = np.ones_like(x)
    norm = np.sqrt(x * x + y * y + z * z)
    x, y, z = x / norm, y / norm, z / norm
    sin_p, cos_p = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
    y, z = y * cos_p + z * sin_p, -y * sin_p + z * cos_p
    sin_y, cos_y = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    x, z = x * cos_y + z * sin_y, -x * sin_y + z * cos_y
    return np.degrees(np.arctan2(x, z)), np.degrees(np.arcsin(np.clip(y, -1.0, 1.0)))


def equirect_share(lon: Any, lat: Any) -> tuple[Any, Any]:
    """Longitude and latitude (degrees) as shares of the equirect frame, x wrapped into 0..1."""
    return (np.asarray(lon) / 360.0 + 0.5) % 1.0, 0.5 - np.asarray(lat) / 180.0


def view_maps(
    width: int, height: int, size: int, fov: float, yaw: float, pitch: float
) -> tuple[Any, Any]:
    """`cv2.remap` maps that sample an equirect frame into a square view (x wraps at the edge)."""
    grid_u, grid_v = np.meshgrid(np.arange(size) + 0.5, np.arange(size) + 0.5)
    lon, lat = view_rays(grid_u, grid_v, size, fov, yaw, pitch)
    x, y = equirect_share(lon, lat)
    return (x * width - 0.5).astype(np.float32), (y * height - 0.5).astype(np.float32)


def view_point_to_equirect(
    u: float, v: float, size: int, fov: float, yaw: float, pitch: float
) -> tuple[float, float]:
    """Where a view pixel sits on the equirect frame, as shares 0..1."""
    lon, lat = view_rays(u, v, size, fov, yaw, pitch)
    x, y = equirect_share(lon, lat)
    return float(x), float(y)


def centered_on(x: float, y: float) -> tuple[float, float]:
    """The view yaw and pitch that put an equirect point (shares) at the view center."""
    pitch = max(-MAX_VIEW_PITCH, min(MAX_VIEW_PITCH, (0.5 - y) * 180.0))
    return (x - 0.5) * 360.0, pitch
