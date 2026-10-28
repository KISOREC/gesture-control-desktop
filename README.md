# Gesture Desktop Assistant

This Windows desktop application uses MediaPipe and OpenCV for webcam hand tracking and PyAutoGUI for local mouse/keyboard control. It also includes a small local command assistant, on-demand Windows UI Automation/OCR screen inspection, and optional local voice recognition.

## Requirements and installation

- Windows 10/11
- Python 3.10–3.12 (MediaPipe is pinned below 0.10.22 because the app uses `mp.solutions`)
- A working webcam and permission to control the mouse and keyboard

Open PowerShell in this project directory and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

If PowerShell blocks virtual-environment activation, run this only in the current PowerShell process, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

For an existing environment, activate it and run `python -m pip install -r requirements.txt`, then `python main.py`. Keep MediaPipe below `0.10.22`; newer releases do not provide the legacy `mp.solutions` API used here.

## Controls

- `q` in the camera window: quit and release any held left mouse button.
- `i`: inspect the current pointer location.
- `v`: start/stop optional local push-to-talk voice input.
- Type assistant commands in the PowerShell console running the app. Examples: `where am I pointing`, `click Search`, `scroll down`, `go back`, and `type hello`.
- For text entry, review the proposed text, then type `confirm` in the console; use `cancel` to discard it.

## Hand gestures

- **Left hand, index finger only:** move the cursor. Open palm and other multi-finger poses do not move it.
- **Thumb and index pinch:** hold the left mouse button to drag; separate them to release.
- **Peace sign:** double left-click.
- **Fist:** right-click.
- **Index, middle, and ring fingers up with pinky folded:** send `Win+Ctrl+O` once after three consecutive frames to open Windows On-Screen Keyboard. Release the pose before triggering it again.
- **All four fingers up with thumb folded:** single left-click, including on the On-Screen Keyboard.
- If the hand leaves view or the app exits, a held drag is released.
- **Right-hand swipe:** send the corresponding arrow-key press.

## Screen understanding and privacy

The default assistant is local-only. It can inspect accessible controls through Windows UI Automation; OCR is a text-only fallback and never makes OCR results clickable. Install the Tesseract OCR application separately and make `tesseract.exe` available on `PATH` to enable that fallback. Without it, the app reports OCR as unavailable.

Voice recognition is optional. To enable it, install `vosk` and `sounddevice`, download a local Vosk model, and set `VOSK_MODEL_PATH` to that model directory before starting the app. No cloud service or screenshot upload is configured.

This is a safe local MVP, not a general-purpose AI agent: command parsing is deterministic, desktop actions are restricted to an allowlist, and text entry requires confirmation. It does not execute shell commands. A floating assistant panel, general AI model/provider, and live acceptance testing across different Windows applications are not included.

## Tests

Run the automated tests from the project directory:

```powershell
python -m unittest discover -s tests -t . -v
```

## Acknowledgments

Hand landmark detection uses [MediaPipe](https://mediapipe.dev/) and [OpenCV](https://opencv.org/). This project is based on [baukk/Gesture-Recognition](https://github.com/baukk/Gesture-Recognition).
