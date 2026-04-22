from __future__ import annotations

from types import SimpleNamespace

from app.inference import driver as driver_module


class FakeLandmarkerInstance:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_driver_detector_initializes_with_model_asset_buffer(monkeypatch):
    captured = {}
    fake_landmarker = FakeLandmarkerInstance()

    class FakeBaseOptions:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    class FakeFaceLandmarkerOptions:
        def __init__(self, **kwargs) -> None:
            captured["option_kwargs"] = kwargs

    class FakeFaceLandmarker:
        @staticmethod
        def create_from_options(options):
            captured["options"] = options
            return fake_landmarker

    monkeypatch.setattr(driver_module, "MEDIAPIPE_AVAILABLE", True)
    monkeypatch.setattr(
        driver_module,
        "mp_python",
        SimpleNamespace(BaseOptions=FakeBaseOptions),
    )
    monkeypatch.setattr(
        driver_module,
        "mp_vision",
        SimpleNamespace(
            FaceLandmarker=FakeFaceLandmarker,
            FaceLandmarkerOptions=FakeFaceLandmarkerOptions,
            RunningMode=SimpleNamespace(VIDEO="VIDEO"),
        ),
    )
    monkeypatch.setattr(
        driver_module.DriverDetector,
        "_load_model_asset_buffer",
        classmethod(lambda cls: b"model-bytes"),
    )

    detector = driver_module.DriverDetector()

    assert captured["model_asset_buffer"] == b"model-bytes"
    assert "model_asset_path" not in captured
    assert detector.face_landmarker is fake_landmarker

    detector.close()
    assert fake_landmarker.closed is True
