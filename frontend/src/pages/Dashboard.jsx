import { useState, useEffect, useRef } from "react";
import {
  getCameraSources,
  startCamera,
  stopCamera,
  setCameraMode,
} from "../services/api";

function Dashboard() {
  const [cameraState, setCameraState] = useState(null);
  const [driverState, setDriverState] = useState(null);
  const [driverEvents, setDriverEvents] = useState([]);
  const [sources, setSources] = useState([]);
  const [selectedSourceId, setSelectedSourceId] = useState("webcam:0");
  const [frameData, setFrameData] = useState(null);
  const [error, setError] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  
  const liveWsRef = useRef(null);
  const eventsWsRef = useRef(null);

  // Helper to create source ID string
  const makeSourceId = (s) => `${s.source_type}:${s.source_id}`;

  // Helper to parse source ID string
  const parseSourceId = (id) => {
    const idx = id.indexOf(":");
    if (idx === -1) return { type: id, id: "0" };
    return { type: id.substring(0, idx), id: id.substring(idx + 1) };
  };

  // Connect to WebSockets
  useEffect(() => {
    // Backend WebSocket base URL
    const wsBase = "ENV_BACKEND_WS_ORIGIN";
    
    // Live feed WebSocket
    const connectLive = () => {
      const wsUrl = `${wsBase}/ws/live`;
      console.log("[Dashboard] Connecting to live WebSocket:", wsUrl);
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        console.log("[Dashboard] Live WS connected");
        setWsConnected(true);
      };
      
      ws.onclose = () => {
        console.log("[Dashboard] Live WS disconnected");
        setWsConnected(false);
        setTimeout(connectLive, 2000);
      };
      
      ws.onerror = (e) => {
        console.error("[Dashboard] Live WS error:", e);
      };
      
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "frame" && msg.data) {
            setFrameData(msg.data);
          }
        } catch (e) {
          console.error("[Dashboard] Parse error", e);
        }
      };
      
      liveWsRef.current = ws;
    };
    
    // Events WebSocket
    const connectEvents = () => {
      const wsUrl = `${wsBase}/ws/events`;
      console.log("[Dashboard] Connecting to events WebSocket:", wsUrl);
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => console.log("[Dashboard] Events WS connected");
      ws.onclose = () => setTimeout(connectEvents, 2000);
      ws.onerror = (e) => console.error("[Dashboard] Events WS error:", e);
      
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "status" && msg.camera) {
            setCameraState(msg.camera);
            if (msg.camera.driver) {
              setDriverState(msg.camera.driver);
            }
          } else if (msg.type === "driver_event") {
            console.log("[Dashboard] Driver event:", msg);
            setDriverEvents(prev => [{
              id: Date.now(),
              event_type: msg.event_type,
              timestamp: msg.timestamp,
              confidence: msg.confidence,
              details: msg.details
            }, ...prev].slice(0, 10)); // Keep last 10 events
          }
        } catch (e) {
          console.error("[Dashboard] Parse error", e);
        }
      };
      
      eventsWsRef.current = ws;
    };
    
    connectLive();
    connectEvents();
    
    return () => {
      if (liveWsRef.current) liveWsRef.current.close();
      if (eventsWsRef.current) eventsWsRef.current.close();
    };
  }, []);

  // Load camera sources
  useEffect(() => {
    console.log("[Dashboard] Loading camera sources...");
    getCameraSources()
      .then((data) => {
        console.log("[Dashboard] Available sources:", data);
        setSources(data || []);
        // Set default selection to first source if available
        if (data && data.length > 0) {
          const firstId = makeSourceId(data[0]);
          console.log("[Dashboard] Default source:", firstId);
          setSelectedSourceId(firstId);
        }
      })
      .catch((e) => {
        console.error("[Dashboard] Failed to load sources:", e);
      });
  }, []);

  const handleStart = async () => {
    const parsed = parseSourceId(selectedSourceId);
    console.log("[Dashboard] selectedSourceId:", selectedSourceId);
    console.log("[Dashboard] Parsed source:", parsed);
    
    setError(null);
    setIsStarting(true);
    
    try {
      console.log("[Dashboard] Calling startCamera API...");
      const result = await startCamera(parsed.type, parsed.id);
      console.log("[Dashboard] Start success:", result);
      if (result.error) {
        setError(result.error);
      }
    } catch (e) {
      console.error("[Dashboard] Start failure:", e);
      setError("Failed to start camera: " + (e.message || "Unknown error"));
    } finally {
      setIsStarting(false);
      console.log("[Dashboard] isStarting reset to false");
    }
  };

  const handleReset = () => {
    console.log("[Dashboard] Manual reset");
    setIsStarting(false);
    setError(null);
    setCameraState(null);
    setFrameData(null);
    setDriverState(null);
  };

  const handleStop = async () => {
    console.log("[Dashboard] Stop button clicked");
    try {
      setError(null);
      const result = await stopCamera();
      setFrameData(null);
      setDriverState(null);
      // Update camera state from API response
      setCameraState(result);
      console.log("[Dashboard] Stop success, camera state:", result);
    } catch (e) {
      console.error("[Dashboard] Stop camera error:", e);
      setError("Failed to stop camera");
      // Reset state anyway on error
      setCameraState({
        active: false,
        source_type: "none",
        source_id: "",
        fps: 0,
        frames_captured: 0,
        mode: "idle",
        error: ""
      });
    }
  };

  const handleModeChange = async (mode) => {
    try {
      await setCameraMode(mode);
      if (mode !== "driver") {
        setDriverState(null);
      }
    } catch (e) {
      setError("Failed to change mode");
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-2 rounded mb-4">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Video Feed */}
        <div className="bg-white rounded-lg shadow p-4">
          <h2 className="font-semibold mb-4">Live Feed</h2>
          <div className="aspect-video bg-gray-900 rounded flex items-center justify-center overflow-hidden">
            {frameData ? (
              <img
                src={`data:image/jpeg;base64,${frameData}`}
                alt="Live feed"
                className="w-full h-full object-contain"
              />
            ) : (
              <p className="text-white">Camera not active</p>
            )}
          </div>

          {/* Camera Controls */}
          <div className="mt-4 space-y-3">
            <div className="flex gap-2">
              <select
                value={selectedSourceId}
                onChange={(e) => {
                  const newValue = e.target.value;
                  console.log("[Dashboard] Source selected:", newValue);
                  setSelectedSourceId(newValue);
                }}
                disabled={cameraState?.active}
                className="border rounded px-3 py-2 flex-1 disabled:bg-gray-100"
              >
                {sources.length === 0 && (
                  <option value="webcam:0">Webcam 0 (default)</option>
                )}
                {sources.map((s) => {
                  const id = makeSourceId(s);
                  return (
                    <option key={id} value={id}>
                      {s.name}
                    </option>
                  );
                })}
              </select>
            </div>

            <div className="flex gap-2">
              <button
                onClick={handleStart}
                disabled={cameraState?.active || isStarting}
                className="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600 disabled:bg-gray-300"
              >
                {isStarting ? "Starting..." : "Start Camera"}
              </button>
              <button
                onClick={handleStop}
                disabled={!cameraState?.active && !isStarting}
                className="bg-red-500 text-white px-4 py-2 rounded hover:bg-red-600 disabled:bg-gray-300"
              >
                Stop Camera
              </button>
              <button
                onClick={handleReset}
                className="bg-gray-500 text-white px-4 py-2 rounded hover:bg-gray-600"
                title="Reset UI state if stuck"
              >
                Reset
              </button>
            </div>
          </div>
        </div>

        {/* Status Panel */}
        <div className="bg-white rounded-lg shadow p-4">
          <h2 className="font-semibold mb-4">System Status</h2>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span>Camera:</span>
              <span className={cameraState?.active ? "text-green-600 font-medium" : "text-gray-500"}>
                {cameraState?.active ? "Active" : "Inactive"}
              </span>
            </div>
            <div className="flex justify-between">
              <span>Source:</span>
              <span className="font-medium">{cameraState?.source_type || "None"}</span>
            </div>
            <div className="flex justify-between">
              <span>FPS:</span>
              <span className="font-medium">{cameraState?.fps?.toFixed(1) || "0"}</span>
            </div>
            <div className="flex justify-between">
              <span>Frames:</span>
              <span className="font-medium">{cameraState?.frames_captured || 0}</span>
            </div>
            <div className="flex justify-between">
              <span>WebSocket:</span>
              <span className={wsConnected ? "text-green-600" : "text-red-500"}>
                {wsConnected ? "Connected" : "Disconnected"}
              </span>
            </div>
            {cameraState?.error && (
              <div className="text-red-500 text-sm">{cameraState.error}</div>
            )}

            {/* Mode Selection */}
            <div className="pt-3 border-t">
              <label className="block text-sm font-medium mb-2">Processing Mode</label>
              <div className="flex gap-2">
                {["idle", "gate", "driver"].map((mode) => (
                  <button
                    key={mode}
                    onClick={() => handleModeChange(mode)}
                    className={`px-3 py-1 rounded capitalize ${
                      cameraState?.mode === mode
                        ? "bg-blue-500 text-white"
                        : "bg-gray-200 hover:bg-gray-300"
                    }`}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Driver Monitoring Panel - Only show in driver mode */}
        {cameraState?.mode === "driver" && (
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="font-semibold mb-4">Driver Monitoring</h2>
            {driverState ? (
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span>Face Detected:</span>
                  <span className={driverState.face_detected ? "text-green-600" : "text-red-500"}>
                    {driverState.face_detected ? "Yes" : "No"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Eye Aspect Ratio:</span>
                  <span className={driverState.ear_left < 0.2 ? "text-red-500 font-bold" : ""}>
                    L: {driverState.ear_left?.toFixed(2)} / R: {driverState.ear_right?.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Mouth (MAR):</span>
                  <span className={driverState.mar > 0.6 ? "text-orange-500 font-bold" : ""}>
                    {driverState.mar?.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Head Pose:</span>
                  <span className={Math.abs(driverState.head_yaw) > 30 || Math.abs(driverState.head_pitch) > 20 ? "text-orange-500 font-bold" : ""}>
                    Yaw: {driverState.head_yaw?.toFixed(1)}° / Pitch: {driverState.head_pitch?.toFixed(1)}°
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Eyes Closed:</span>
                  <span className={driverState.eyes_closed_duration > 1 ? "text-red-500 font-bold" : ""}>
                    {driverState.eyes_closed_duration?.toFixed(1)}s
                  </span>
                </div>
                
                {/* Warning indicators */}
                <div className="pt-3 border-t space-y-2">
                  {driverState.is_fatigued && (
                    <div className="bg-red-100 border border-red-400 text-red-700 px-3 py-2 rounded text-center font-bold">
                      ⚠️ FATIGUE WARNING
                    </div>
                  )}
                  {driverState.is_distracted && (
                    <div className="bg-orange-100 border border-orange-400 text-orange-700 px-3 py-2 rounded text-center font-bold">
                      ⚠️ DISTRACTION WARNING
                    </div>
                  )}
                  {!driverState.is_fatigued && !driverState.is_distracted && driverState.face_detected && (
                    <div className="bg-green-100 border border-green-400 text-green-700 px-3 py-2 rounded text-center">
                      ✓ Driver Alert
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-gray-500">Waiting for driver data...</p>
            )}
          </div>
        )}

        {/* Driver Events Panel */}
        {cameraState?.mode === "driver" && (
          <div className="bg-white rounded-lg shadow p-4">
            <h2 className="font-semibold mb-4">Recent Driver Events</h2>
            {driverEvents.length > 0 ? (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {driverEvents.map((ev) => (
                  <div
                    key={ev.id}
                    className={`px-3 py-2 rounded text-sm ${
                      ev.event_type === "FATIGUE"
                        ? "bg-red-50 border border-red-200"
                        : "bg-orange-50 border border-orange-200"
                    }`}
                  >
                    <div className="flex justify-between">
                      <span className="font-medium">{ev.event_type}</span>
                      <span className="text-gray-500">
                        {new Date(ev.timestamp * 1000).toLocaleTimeString()}
                      </span>
                    </div>
                    <div className="text-gray-600">{ev.details}</div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-gray-500">No events yet</p>
            )}
          </div>
        )}

        {/* Info */}
        <div className="bg-white rounded-lg shadow p-4 lg:col-span-2">
          <h2 className="font-semibold mb-4">Instructions</h2>
          <ul className="text-gray-600 space-y-1 text-sm">
            <li>1. Select camera source (Webcam 0 is usually the default)</li>
            <li>2. Click "Start Camera" to begin streaming</li>
            <li>3. Select "driver" mode to enable fatigue/distraction detection</li>
            <li>4. Face the camera - the system will track your eyes and head pose</li>
            <li>5. Close eyes for 2+ seconds to trigger fatigue warning</li>
            <li>6. Turn head away to trigger distraction warning</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
