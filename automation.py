from __future__ import annotations

import csv
import ctypes
import re
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

import cv2
import keyboard
import numpy as np
import pyautogui
import pygetwindow as gw
from PIL import ImageGrab

from config_loader import resolve_resource_path
from models import RunStatistics, ScreenTemplate


user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0


class AutomationEngine:
    def __init__(
        self,
        config: dict,
        selected_title: str,
        budget: int | None = None,
        allow_move: bool = False,
        ui_hooks: dict | None = None,
    ) -> None:
        self.config = config
        self.selected_title = selected_title
        self.budget = budget
        self.allow_move = allow_move
        self.ui_hooks = ui_hooks or {}
        self.loop_active = False
        self.loop_finished = True

        timing = self.config["flow"]["timing"]
        self.mouse_sleep = float(timing.get("mouse_sleep", 0.3))
        self.screenshot_sleep = float(timing.get("screenshot_sleep", 0.3))
        self.default_poll = float(timing.get("poll_interval", 1.0))

        self.window = self._find_window(selected_title)
        self.stats = RunStatistics()
        self.templates = self._load_templates(self.config.get("templates", []))
        self.debug_dir = Path(self.config["app"].get("debug_dir", "debug"))
        self.input_mode = self.config["window"].get("input_mode", "pyautogui")

    def _safe_window_call(self, operation, *, swallow: bool = True):
        try:
            return operation()
        except Exception:
            if swallow:
                return None
            raise

    def _find_window(self, title: str):
        windows = gw.getWindowsWithTitle(title)
        window = next((win for win in windows if win.title == title), None)
        if window is None:
            raise RuntimeError(f"Window not found: {title}")
        return window

    def _load_templates(self, templates: list[dict]) -> dict[str, ScreenTemplate]:
        loaded: dict[str, ScreenTemplate] = {}
        assets_dir = resolve_resource_path(self.config, self.config["app"].get("assets_dir", "assets"))
        for item in templates:
            image_path = assets_dir / item["path"] if assets_dir is not None else Path(item["path"])
            image = cv2.imread(str(image_path))
            if image is None:
                raise FileNotFoundError(f"Asset not found: {image_path}")
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            loaded[item["name"]] = ScreenTemplate(
                name=item["name"],
                path=item["path"],
                threshold=float(item.get("threshold", 0.8)),
                min_scale=float(item.get("min_scale", 0.6)),
                max_scale=float(item.get("max_scale", 1.0)),
                scale_step=float(item.get("scale_step", 0.05)),
                image=image,
            )
        return loaded

    def start(self) -> None:
        if self.loop_active or not self.loop_finished:
            return
        self.loop_active = True
        self.loop_finished = False
        self.stats.restart()
        threading.Thread(target=self._check_keypress, daemon=True).start()
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _check_keypress(self) -> None:
        while self.loop_active and not self.loop_finished:
            self.loop_active = not keyboard.is_pressed("esc")
            time.sleep(0.05)
        self.loop_active = False

    def _run_loop(self) -> None:
        try:
            self._prepare_window()
            self._run_actions(self.config["flow"].get("startup_actions", []))

            loop_steps = self.config["flow"].get("loop_steps", [])
            if not loop_steps:
                raise RuntimeError("No loop_steps configured.")

            while self.loop_active:
                for step in loop_steps:
                    if not self.loop_active:
                        break
                    self.stats.last_step = step.get("name", "")
                    if self.ui_hooks.get("on_step"):
                        self.ui_hooks["on_step"](self.stats.last_step)
                    self._execute_step(step)

                self.stats.loop_count += 1
                if self.ui_hooks.get("on_loop"):
                    self.ui_hooks["on_loop"](self.stats.loop_count)

                if self.budget and self.stats.loop_count >= self.budget:
                    break

            self._finish()
        except Exception as error:
            self._finish(error)

    def _prepare_window(self) -> None:
        if self.window.isMaximized or self.window.isMinimized:
            self._safe_window_call(self.window.restore)
        if not self.allow_move:
            self._safe_window_call(lambda: self.window.moveTo(0, 0))

        geometry = self.config["window"].get("geometry", {})
        width = int(geometry.get("width", self.window.width))
        height = int(geometry.get("height", self.window.height))
        self._safe_window_call(lambda: self.window.resizeTo(width, height))

        self._safe_window_call(self.window.activate)
        time.sleep(self.mouse_sleep)

    def _window_handle(self):
        return getattr(self.window, "_hWnd", None) or getattr(self.window, "hWnd", None)

    def _screen_size(self) -> tuple[int, int]:
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

    def _screen_to_client(self, x: float, y: float) -> tuple[int, int] | None:
        hwnd = self._window_handle()
        if hwnd is None:
            return None
        point = wintypes.POINT(int(x), int(y))
        result = user32.ScreenToClient(hwnd, ctypes.byref(point))
        if result == 0:
            return None
        return point.x, point.y

    def _emit_cursor_click(self, x: float, y: float, clicks: int, interval: float) -> None:
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.03)
        for index in range(clicks):
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.03)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            if index < clicks - 1:
                time.sleep(interval)

    def _emit_window_click(self, x: float, y: float, clicks: int, interval: float) -> None:
        hwnd = self._window_handle()
        client_point = self._screen_to_client(x, y)
        if hwnd is None or client_point is None:
            return
        cx, cy = client_point
        lparam = (cy << 16) | (cx & 0xFFFF)
        for index in range(clicks):
            user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
            user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
            time.sleep(0.02)
            user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
            if index < clicks - 1:
                time.sleep(interval)

    def _emit_sendinput_click(self, x: float, y: float, clicks: int, interval: float) -> None:
        screen_width, screen_height = self._screen_size()
        if screen_width <= 1 or screen_height <= 1:
            return
        abs_x = int(x * 65535 / (screen_width - 1))
        abs_y = int(y * 65535 / (screen_height - 1))
        user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, abs_x, abs_y, 0, 0)
        time.sleep(0.03)
        for index in range(clicks):
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.03)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            if index < clicks - 1:
                time.sleep(interval)

    def _emit_pyautogui_click(self, x: float, y: float, clicks: int, interval: float) -> None:
        pyautogui.moveTo(x, y)
        pyautogui.click(clicks=clicks, interval=interval)

    def _emit_pyautogui_drag(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        *,
        hold_before: float,
        hold_after_move: float,
        duration: float,
        button: str,
    ) -> None:
        pyautogui.moveTo(start_x, start_y)
        time.sleep(hold_before)
        pyautogui.mouseDown(button=button)
        time.sleep(hold_before)
        pyautogui.moveTo(end_x, end_y, duration=duration)
        time.sleep(hold_after_move)
        pyautogui.mouseUp(button=button)

    def _move_cursor_to(self, x: float, y: float) -> None:
        self._safe_window_call(self.window.activate)
        if self.input_mode == "window_message":
            return
        if self.input_mode == "win32_cursor":
            user32.SetCursorPos(int(x), int(y))
            return
        if self.input_mode == "sendinput_cursor":
            screen_width, screen_height = self._screen_size()
            if screen_width > 1 and screen_height > 1:
                abs_x = int(x * 65535 / (screen_width - 1))
                abs_y = int(y * 65535 / (screen_height - 1))
                user32.mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, abs_x, abs_y, 0, 0)
            return
        pyautogui.moveTo(x, y)

    def probe_point(self, x_ratio: float, y_ratio: float, *, click: bool = False, clicks: int = 1) -> tuple[int, int]:
        self._prepare_window()
        x, y = self._resolve_xy(x_ratio, y_ratio)
        if self.ui_hooks.get("on_action"):
            action_name = "click" if click else "move"
            self.ui_hooks["on_action"](f"{action_name} probe ({int(x)}, {int(y)})")
        if click:
            self._click_at(x, y, clicks=clicks)
        else:
            self._move_cursor_to(x, y)
        return int(x), int(y)

    def _click_at(self, x: float, y: float, clicks: int = 1, interval: float | None = None) -> None:
        used_interval = float(interval if interval is not None else self.mouse_sleep)
        if self.ui_hooks.get("on_action"):
            self.ui_hooks["on_action"](f"click ({int(x)}, {int(y)}) x{clicks}")

        self._safe_window_call(self.window.activate)
        if self.input_mode == "window_message":
            self._emit_window_click(x, y, clicks, used_interval)
        elif self.input_mode == "sendinput_cursor":
            self._emit_sendinput_click(x, y, clicks, used_interval)
        elif self.input_mode == "win32_cursor":
            self._emit_cursor_click(x, y, clicks, used_interval)
        else:
            self._emit_pyautogui_click(x, y, clicks, used_interval)

    def _drag_between(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        *,
        hold_before: float,
        hold_after_move: float,
        duration: float,
        button: str,
        interpolate: bool = True,
    ) -> None:
        if button != "left":
            raise ValueError("Only left button drag is supported.")
        if self.ui_hooks.get("on_action"):
            self.ui_hooks["on_action"](
                f"drag ({int(start_x)}, {int(start_y)}) -> ({int(end_x)}, {int(end_y)})"
            )

        self._safe_window_call(self.window.activate)
        if self.input_mode == "pyautogui":
            self._emit_pyautogui_drag(
                start_x,
                start_y,
                end_x,
                end_y,
                hold_before=hold_before,
                hold_after_move=hold_after_move,
                duration=duration,
                button=button,
            )
            return
        if self.input_mode == "sendinput_cursor":
            self._move_cursor_to(start_x, start_y)
            time.sleep(hold_before)
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(hold_before)
            if interpolate:
                steps = max(int(duration / 0.016), 8)
                step_delay = duration / steps if duration > 0 else 0
                for i in range(1, steps + 1):
                    t = i / steps
                    ix = start_x + (end_x - start_x) * t
                    iy = start_y + (end_y - start_y) * t
                    self._move_cursor_to(ix, iy)
                    if step_delay > 0:
                        time.sleep(step_delay)
            else:
                self._move_cursor_to(end_x, end_y)
                if duration > 0:
                    time.sleep(duration)
            time.sleep(hold_after_move)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return

        user32.SetCursorPos(int(start_x), int(start_y))
        time.sleep(hold_before)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(hold_before)
        if interpolate:
            steps = max(int(duration / 0.016), 8)
            step_delay = duration / steps if duration > 0 else 0
            for i in range(1, steps + 1):
                t = i / steps
                ix = start_x + (end_x - start_x) * t
                iy = start_y + (end_y - start_y) * t
                user32.SetCursorPos(int(ix), int(iy))
                if step_delay > 0:
                    time.sleep(step_delay)
        else:
            user32.SetCursorPos(int(end_x), int(end_y))
            if duration > 0:
                time.sleep(duration)
        time.sleep(hold_after_move)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def _execute_step(self, step: dict) -> None:
        wait_for = step.get("wait_for")
        if wait_for:
            raw_timeout = step.get("timeout_seconds", 120)
            timeout_seconds = None if raw_timeout is None else float(raw_timeout)
            confirm_matches = int(step.get("confirm_matches", 1))
            search_region = step.get("search_region")
            matched_name = self._wait_for_templates(
                template_names=wait_for,
                timeout_seconds=timeout_seconds,
                poll_interval=float(step.get("poll_interval", self.default_poll)),
                confirm_matches=confirm_matches,
                search_region=search_region,
            )
            if self.ui_hooks.get("on_match"):
                self.ui_hooks["on_match"](matched_name)

            if step.get("click_on_match") and self._last_match_center is not None:
                cx, cy = self._last_match_center
                abs_x = self.window.left + cx
                abs_y = self.window.top + cy
                self._click_at(abs_x, abs_y)
                time.sleep(float(step.get("click_delay_after", 1.0)))

        scan_config = step.get("scan_and_click")
        if scan_config:
            self._scan_and_click(scan_config)

        self._run_actions(step.get("actions", []))

    def _scan_and_click(self, config: dict) -> None:
        verify_name = config["verify_template"]
        verify_template = self.templates[verify_name]
        scan_x = float(config.get("scan_x_ratio", 0.50))
        y_start = float(config.get("scan_y_start", 0.30))
        y_step = float(config.get("scan_y_step", 0.09))
        y_end = float(config.get("scan_y_end", 0.80))
        click_delay = float(config.get("click_delay", 0.8))
        timeout = float(config.get("timeout_seconds", 20))

        started = time.time()
        y = y_start
        while self.loop_active and y <= y_end:
            if (time.time() - started) > timeout:
                break

            x, click_y = self._resolve_xy(scan_x, y)
            self._click_at(x, click_y)
            if self.ui_hooks.get("on_action"):
                self.ui_hooks["on_action"](f"scan click y={y:.2f}")
            time.sleep(click_delay)

            screenshot = self.take_screenshot()
            if screenshot is not None:
                screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)
                if self._find_template(screenshot_gray, verify_template) is not None:
                    if self.ui_hooks.get("on_match"):
                        self.ui_hooks["on_match"](verify_name)
                    return

            y += y_step

        raise TimeoutError(
            f"scan_and_click: could not verify {verify_name} after scanning"
        )

    def _wait_for_templates(
        self,
        template_names: list[str],
        timeout_seconds: float | None,
        poll_interval: float,
        confirm_matches: int = 1,
        search_region: dict | None = None,
    ) -> str:
        started = time.time()
        last_screenshot = None
        consecutive_hits = 0
        last_match_name = None
        self._last_match_center = None
        while self.loop_active:
            if timeout_seconds is not None and timeout_seconds > 0:
                if (time.time() - started) > timeout_seconds:
                    break
            screenshot = self.take_screenshot()
            if screenshot is None:
                time.sleep(poll_interval)
                continue
            last_screenshot = screenshot
            screenshot_gray = cv2.cvtColor(screenshot, cv2.COLOR_RGB2GRAY)

            region_offset_x = 0
            region_offset_y = 0
            search_area = screenshot_gray
            if search_region:
                sh, sw = screenshot_gray.shape[:2]
                x1 = int(sw * search_region.get("x_min", 0))
                x2 = int(sw * search_region.get("x_max", 1))
                y1 = int(sh * search_region.get("y_min", 0))
                y2 = int(sh * search_region.get("y_max", 1))
                search_area = screenshot_gray[y1:y2, x1:x2]
                region_offset_x = x1
                region_offset_y = y1

            current_match_name = None
            current_match_result = None
            for name in template_names:
                template = self.templates[name]
                match_result = self._find_template(search_area, template)
                if match_result is not None:
                    current_match_name = name
                    current_match_result = match_result
                    break

            if current_match_name is not None:
                if current_match_name == last_match_name:
                    consecutive_hits += 1
                else:
                    last_match_name = current_match_name
                    consecutive_hits = 1

                if consecutive_hits >= max(confirm_matches, 1):
                    if current_match_result is not None:
                        mx, my, mw, mh = current_match_result
                        self._last_match_center = (
                            mx + mw // 2 + region_offset_x,
                            my + mh // 2 + region_offset_y,
                        )
                    return current_match_name
            else:
                consecutive_hits = 0
                last_match_name = None

            time.sleep(poll_interval)

        if last_screenshot is not None:
            self._save_debug_screenshot(last_screenshot, f"timeout_{'_'.join(template_names)}")
        raise TimeoutError(
            f"Timed out waiting for templates: {', '.join(template_names)}"
        )

    def _run_actions(self, actions: list[dict]) -> None:
        for action in actions:
            if not self.loop_active and action.get("type") != "wait":
                break
            repeat = int(action.get("repeat", 1))
            for _ in range(repeat):
                self._run_single_action(action)

    def _run_single_action(self, action: dict) -> None:
        action_type = action["type"]
        if action_type == "wait":
            time.sleep(float(action.get("seconds", 0)))
            return

        if action_type == "activate":
            self._safe_window_call(self.window.activate)
            time.sleep(float(action.get("delay_after", 0)))
            return

        if action_type == "click":
            x, y = self._resolve_xy(float(action["x_ratio"]), float(action["y_ratio"]))
            self._click_at(
                x,
                y,
                clicks=int(action.get("clicks", 1)),
                interval=float(action.get("interval", self.mouse_sleep)),
            )
            time.sleep(float(action.get("delay_after", self.mouse_sleep)))
            return

        if action_type == "drag":
            start_x, start_y = self._resolve_xy(
                float(action["start_x_ratio"]),
                float(action["start_y_ratio"]),
            )
            end_x, end_y = self._resolve_xy(
                float(action["end_x_ratio"]),
                float(action["end_y_ratio"]),
            )
            self._drag_between(
                start_x,
                start_y,
                end_x,
                end_y,
                hold_before=float(action.get("hold_before", 0.05)),
                hold_after_move=float(action.get("hold_after_move", 0.05)),
                duration=float(action.get("duration", 0.05)),
                button=action.get("button", "left"),
                interpolate=action.get("interpolate", True),
            )
            time.sleep(float(action.get("delay_after", self.screenshot_sleep)))
            return

        raise ValueError(f"Unsupported action type: {action_type}")

    def _resolve_xy(self, x_ratio: float, y_ratio: float) -> tuple[float, float]:
        return (
            self.window.left + self.window.width * x_ratio,
            self.window.top + self.window.height * y_ratio,
        )

    def take_screenshot(self):
        try:
            self._safe_window_call(self.window.activate)
            region = [self.window.left, self.window.top, self.window.width, self.window.height]
            image = ImageGrab.grab(
                bbox=(region[0], region[1], region[0] + region[2], region[1] + region[3]),
                all_screens=True,
            )
            return np.array(image)
        except Exception:
            return None

    def _find_template(self, screenshot_gray, template: ScreenTemplate):
        best_score = -1.0
        best_loc = None
        best_size = None

        scale = template.min_scale
        while scale <= template.max_scale + 1e-9:
            width = int(template.image.shape[1] * scale)
            height = int(template.image.shape[0] * scale)
            if width < 20 or height < 20:
                scale += template.scale_step
                continue
            if width >= screenshot_gray.shape[1] or height >= screenshot_gray.shape[0]:
                scale += template.scale_step
                continue

            interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
            resized = cv2.resize(template.image, (width, height), interpolation=interpolation)
            result = cv2.matchTemplate(screenshot_gray, resized, cv2.TM_CCOEFF_NORMED)
            _, max_value, _, max_loc = cv2.minMaxLoc(result)
            if max_value > best_score:
                best_score = float(max_value)
                best_loc = max_loc
                best_size = (width, height)
            scale += template.scale_step

        if best_score >= template.threshold and best_loc is not None:
            return int(best_loc[0]), int(best_loc[1]), best_size[0], best_size[1]
        return None

    def _finish(self, error: Exception | None = None) -> None:
        try:
            if error is not None:
                screenshot = self.take_screenshot()
                if screenshot is not None:
                    self._save_debug_screenshot(screenshot, "last_error_frame")
            self._write_history()
        finally:
            self.loop_active = False
            self.loop_finished = True
            if self.ui_hooks.get("on_stop"):
                self.ui_hooks["on_stop"](error, self.stats)

    def _save_debug_screenshot(self, screenshot, name: str) -> None:
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        output = self.debug_dir / f"{name}.png"
        cv2.imwrite(str(output), cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR))

    def _write_history(self) -> None:
        history_dir = Path(self.config["app"].get("history_dir", "history"))
        history_dir.mkdir(parents=True, exist_ok=True)

        prefix = self.config["app"].get("history_prefix", "run")
        safe_prefix = re.sub(r"[^A-Za-z0-9_-]+", "", prefix) or "run"
        file_name = f"{safe_prefix}_{datetime.now().strftime('%Y%m%d')}.csv"
        path = history_dir / file_name
        has_header = path.exists()

        with path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if not has_header:
                writer.writerow(["Time", "Duration", "Loops", "Last step"])
            writer.writerow(
                [
                    self.stats.start_time.isoformat(sep=" ", timespec="seconds"),
                    str(datetime.now() - self.stats.start_time),
                    self.stats.loop_count,
                    self.stats.last_step,
                ]
            )


def discover_window_titles(config: dict) -> list[str]:
    all_titles = [title for title in gw.getAllTitles() if title]
    recognized = set(config["window"].get("recognized_titles", []))
    pattern = config["window"].get("title_pattern")

    matches = [title for title in all_titles if title in recognized]
    if pattern:
        compiled = re.compile(pattern, re.UNICODE)
        matches.extend(title for title in all_titles if compiled.fullmatch(title))

    if matches:
        return sorted(set(matches))
    return sorted(set(all_titles))
