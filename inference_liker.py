"""
inference_liker.py — Self-contained captcha inference for the liker Lambda.
Mirrors inference.py from the uploader project so the liker folder can later
live as a standalone repository with no import dependency on the uploader.
"""

import json
import logging

import numpy as np
import onnxruntime
from PIL import Image

from config import LABELS_FILE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load labels and build character mappings
# ---------------------------------------------------------------------------
with open(LABELS_FILE, "r") as _f:
    _data = json.load(_f)

_labels = list(_data.values())
_characters = sorted(set(c for label in _labels for c in label))
_char_to_idx = {char: idx + 1 for idx, char in enumerate(_characters)}
_char_to_idx["#"] = 0  # blank symbol
_idx_to_char = {idx: char for char, idx in _char_to_idx.items()}


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------

def _preprocess(image_path, img_width: int, img_height: int) -> np.ndarray:
    image = Image.open(image_path).convert("RGB")
    image = image.resize((img_width, img_height))
    arr = np.array(image)
    mean = np.array([0.485, 0.456, 0.406])
    std = np.array([0.229, 0.224, 0.225])
    arr = (arr / 255.0 - mean) / std
    arr = arr.transpose(2, 0, 1).astype(np.float32)
    return np.expand_dims(arr, axis=0)


# ---------------------------------------------------------------------------
# CTC decode
# ---------------------------------------------------------------------------

def _ctc_decode(seq):
    previous = seq[0]
    decoded = [previous] if previous != 0 else []
    for current in seq[1:]:
        if current != 0:
            if current != previous:
                decoded.append(current)
            elif decoded and decoded[-1] != current:
                decoded.append(current)
        previous = current
    return decoded


def _postprocess(output: np.ndarray) -> str:
    exp_out = np.exp(output - np.max(output, axis=2, keepdims=True))
    softmax = exp_out / np.sum(exp_out, axis=2, keepdims=True)
    predicted = np.argmax(softmax, axis=2).transpose(1, 0)
    decoded = _ctc_decode(predicted[0])
    return "".join(_idx_to_char[i] for i in decoded)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def create_onnx_inference_pipeline(onnx_path, img_width: int, img_height: int):
    """
    Returns a ``predict_fn(image_path) -> str`` closure backed by the given
    ONNX model.  Returns None if the model cannot be loaded.
    """
    try:
        session = onnxruntime.InferenceSession(str(onnx_path))
        logger.info(f"[Inference] ONNX model loaded from {onnx_path}")
    except Exception as e:
        logger.error(f"[Inference] Failed to load ONNX model: {e}")
        return None

    def predict_captcha(image_path):
        inp = _preprocess(image_path, img_width, img_height)
        outs = session.run(None, {session.get_inputs()[0].name: inp})
        result = _postprocess(outs[0])
        return result

    return predict_captcha
