"""Sparse sampled RF cubes: six faces per occupied slot, independent of extent."""
import numpy as np
from matplotlib import colormaps, colors
from matplotlib.cm import ScalarMappable
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

FACES = ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4),
         (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5))
CORNERS = np.array([(x, y, z) for z in (0, 1) for y in (0, 1) for x in (0, 1)])

class SparseMap:
    def __init__(self):
        self.session = None
        self.slots = {}
        self.last_sequence = -1

    def apply(self, record):
        if self.session is None:
            self.session = record['session']
        elif record['session'] != self.session:
            raise ValueError('mixed sessions; open each capture in a fresh map')
        if record['sequence'] < self.last_sequence or (record['sequence'] == self.last_sequence and not record.get('snapshot')):
            raise ValueError('stale export')
        self.last_sequence = record['sequence']
        if record['flags'] & 2:
            return
        slot = record['slot']
        previous = self.slots.get(slot)
        if previous and (previous['voxel'] != record['voxel'] or previous['count'] > record['count']):
            raise ValueError('inconsistent slot update')
        self.slots[slot] = record

def draw(ax, sparse, limits=(-100, -30)):
    ax.clear()
    norm = colors.Normalize(*limits)
    cmap = colormaps['viridis']
    faces, shades, bounds = [], [], []
    for record in sparse.slots.values():
        lower = np.asarray(record['lower_m'], dtype=float)
        vertices = lower + CORNERS * record['size_m']
        faces.extend(vertices[list(face)] for face in FACES)
        shades.extend([cmap(norm(record['mean_dbm']))] * len(FACES))
        bounds.extend((lower, lower + record['size_m']))
    ax.add_collection3d(Poly3DCollection(faces, facecolors=shades, edgecolors='none', alpha=0.8))
    if bounds:
        points = np.asarray(bounds)
        for setter, index in ((ax.set_xlim, 0), (ax.set_ylim, 1), (ax.set_zlim, 2)):
            setter(points[:, index].min(), points[:, index].max())
    ax.set(xlabel='x (m)', ylabel='y (m)', zlabel='z (m)', title='Sampled RF voxels; arithmetic mean RSSI')
    return ScalarMappable(norm=norm, cmap=cmap)
