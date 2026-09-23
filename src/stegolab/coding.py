"""Small ctypes boundary around the exact, native syndrome trellis."""
import ctypes
from functools import lru_cache
import os
from pathlib import Path

import numpy as np

WET = np.iinfo(np.uint32).max


class EmbeddingError(ValueError):
    pass


@lru_cache(maxsize=1)
def library():
    path = Path(__file__).parent / "native" / ("stc.dll" if os.name == "nt" else "stc.so")
    if not path.exists():
        raise RuntimeError("Native engine is missing. Run: python scripts/build_native.py")
    lib = ctypes.CDLL(str(path))
    u8 = np.ctypeslib.ndpointer(dtype=np.uint8, ndim=1, flags="C_CONTIGUOUS")
    u16 = np.ctypeslib.ndpointer(dtype=np.uint16, ndim=1, flags="C_CONTIGUOUS")
    u32 = np.ctypeslib.ndpointer(dtype=np.uint32, ndim=1, flags="C_CONTIGUOUS")
    lib.stc_embed.argtypes = [u8, u32, u8, u16, ctypes.c_uint64, ctypes.c_uint64,
                             ctypes.c_uint32, u8, ctypes.POINTER(ctypes.c_uint64)]
    lib.stc_embed.restype = ctypes.c_int
    lib.stc_extract.argtypes = [u8, u16, ctypes.c_uint64, ctypes.c_uint64,
                               ctypes.c_uint32, u8]
    lib.stc_extract.restype = None
    return lib


def embed(parity, costs, target, matrix, height=10):
    parity = np.ascontiguousarray(parity, dtype=np.uint8)
    target = np.ascontiguousarray(target, dtype=np.uint8)
    matrix = np.ascontiguousarray(matrix, dtype=np.uint16)
    costs = np.ascontiguousarray(costs, dtype=np.uint32)
    if (len(costs) != len(parity) or len(matrix) != len(parity)
            or not 1 <= len(target) <= len(parity) or not 1 <= height <= 15
            or np.any(parity > 1) or np.any(target > 1)
            or np.any(matrix >= 1 << height)):
        raise ValueError("Invalid trellis arrays")
    output = np.empty_like(parity)
    optimum = ctypes.c_uint64()
    status = library().stc_embed(parity, costs, target, matrix, len(parity),
                                  len(target), height, output, ctypes.byref(optimum))
    if status == -1:
        raise EmbeddingError("The requested syndrome is unreachable with the wet constraints")
    if status == -3:
        raise EmbeddingError("Native traceback exceeds the resource limit")
    if status:
        raise RuntimeError(f"Native encoder failed: {status}")
    return output, optimum.value


def extract(parity, m, matrix, height=10):
    parity = np.ascontiguousarray(parity, dtype=np.uint8)
    matrix = np.ascontiguousarray(matrix, dtype=np.uint16)
    if not 1 <= m <= len(parity) or len(matrix) != len(parity):
        raise ValueError("Invalid extraction dimensions")
    if not 1 <= height <= 15 or np.any(parity > 1) or np.any(matrix >= 1 << height):
        raise ValueError("Invalid extraction arrays")
    result = np.zeros(m, dtype=np.uint8)
    library().stc_extract(parity, matrix, len(parity), m, height, result)
    return result
