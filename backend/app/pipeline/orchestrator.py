"""
Processing Orchestrator
Main frame processing loop.
"""
import asyncio
import threading
import time
from typing import Optional, Callable, List

from app.camera.manager import camera_manager, frame_to_base64, Frame
from app.services.events import event_service


class Orchestrator:
    """Orchestrates frame processing pipeline."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.running = False
        self.process_thread: Optional[threading.Thread] = None
        self.frame_callbacks: List[Callable] = []
        self.broadcast_callback: Optional[Callable] = None
        self.process_every_n_frames = 3  # Process every Nth frame for performance
        self._initialized = True
    
    def start(self) -> None:
        """Start processing loop."""
        if self.running:
            return
        
        self.running = True
        self.process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.process_thread.start()
    
    def stop(self) -> None:
        """Stop processing loop."""
        self.running = False
        if self.process_thread:
            self.process_thread.join(timeout=2.0)
            self.process_thread = None
    
    def set_broadcast_callback(self, callback: Callable) -> None:
        """Set callback for broadcasting frames/events."""
        self.broadcast_callback = callback
    
    def add_frame_callback(self, callback: Callable) -> None:
        """Add callback for frame processing."""
        self.frame_callbacks.append(callback)
    
    def _process_loop(self) -> None:
        """Main processing loop."""
        frame_count = 0
        last_state_broadcast = 0
        
        while self.running:
            frame = camera_manager.get_frame(timeout=0.1)
            
            if frame is None:
                # Broadcast state periodically even without frames
                if time.time() - last_state_broadcast > 1.0:
                    self._broadcast_state()
                    last_state_broadcast = time.time()
                continue
            
            frame_count += 1
            
            # Process frame (placeholder - AI will go here)
            annotations = self._process_frame(frame)
            
            # Broadcast frame with annotations
            if self.broadcast_callback and frame_count % self.process_every_n_frames == 0:
                self._broadcast_frame(frame, annotations)
            
            # Broadcast state every second
            if time.time() - last_state_broadcast > 1.0:
                self._broadcast_state()
                last_state_broadcast = time.time()
    
    def _process_frame(self, frame: Frame) -> list:
        """
        Process a single frame.
        Returns annotations list.
        """
        annotations = []
        mode = camera_manager.mode
        
        # Placeholder for AI detection
        # In gate mode: run face + PPE detection
        # In driver mode: run fatigue + distraction + seatbelt detection
        
        if mode == "gate":
            # TODO: Face detection
            # TODO: PPE detection
            pass
        elif mode == "driver":
            # TODO: Fatigue detection
            # TODO: Distraction detection
            # TODO: Seatbelt detection
            pass
        
        # Call any registered callbacks
        for callback in self.frame_callbacks:
            try:
                result = callback(frame, mode)
                if result:
                    annotations.extend(result)
            except Exception as e:
                print(f"Frame callback error: {e}")
        
        return annotations
    
    def _broadcast_frame(self, frame: Frame, annotations: list) -> None:
        """Broadcast frame to WebSocket clients."""
        if not self.broadcast_callback:
            return
        
        try:
            frame_data = frame_to_base64(frame)
            message = {
                "type": "frame",
                "data": frame_data,
                "width": frame.width,
                "height": frame.height,
                "frame_number": frame.frame_number,
                "annotations": annotations
            }
            self.broadcast_callback("live", message)
        except Exception as e:
            print(f"Broadcast frame error: {e}")
    
    def _broadcast_state(self) -> None:
        """Broadcast system state."""
        if not self.broadcast_callback:
            return
        
        try:
            state = camera_manager.get_state()
            message = {
                "type": "status",
                "camera": state.to_dict()
            }
            self.broadcast_callback("events", message)
        except Exception as e:
            print(f"Broadcast state error: {e}")


# Global instance
orchestrator = Orchestrator()
