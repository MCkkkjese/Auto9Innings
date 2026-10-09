"""
棒球手遊自動化腳本 - 系統環境與連線自檢模組 (System Diagnostic Tool)
"""
import os
import sys
import time
import platform
import subprocess
import socket
import json
from typing import Dict, Any, List


class SystemDiagnostics:
    """全面檢查執行環境、模擬器安裝狀態、ADB 服務與依賴庫健康度"""

    @staticmethod
    def check_port(host: str = "127.0.0.1", port: int = 5037, timeout: float = 1.0) -> bool:
        """檢查特定 Port 是否開啟 (預設 ADB 5037)"""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    @staticmethod
    def get_installed_emulators() -> List[Dict[str, str]]:
        """掃描常見 Windows / macOS 模擬器 App 與其內建的 adb 路徑"""
        known_apps = [
            # Windows 模擬器
            ("BlueStacks 5 (Windows)", r"C:\Program Files\BlueStacks_nxt\HD-Player.exe", r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"),
            ("BlueStacks 4 (Windows)", r"C:\Program Files\BlueStacks\HD-Player.exe", r"C:\Program Files\BlueStacks\HD-Adb.exe"),
            ("LDPlayer 9 (Windows)", r"C:\LDPlayer\LDPlayer9\dnplayer.exe", r"C:\LDPlayer\LDPlayer9\adb.exe"),
            ("LDPlayer 4 (Windows)", r"C:\LDPlayer\LDPlayer4\dnplayer.exe", r"C:\LDPlayer\LDPlayer4\adb.exe"),
            ("Nox App Player (Windows)", r"C:\Program Files\Nox\bin\Nox.exe", r"C:\Program Files\Nox\bin\nox_adb.exe"),
            ("MuMu Player 12 (Windows)", r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\MuMuPlayer.exe", r"C:\Program Files\Netease\MuMuPlayerGlobal-12.0\shell\adb.exe"),
            # macOS 模擬器
            ("BlueStacks (macOS)", "/Applications/BlueStacks.app", "/Applications/BlueStacks.app/Contents/MacOS/hd-adb"),
            ("BlueStacks Air (macOS)", "/Applications/BlueStacks Air multi-instance manager.app", "/Applications/BlueStacks Air multi-instance manager.app/Contents/MacOS/hd-adb"),
            ("MuMu Player (macOS)", "/Applications/MuMuPlayer.app", "/Applications/MuMuPlayer.app/Contents/MacOS/adb"),
            ("MuMu Pro (macOS)", "/Applications/Netease/MuMuPlayer/Contents/MacOS/adb", "/Applications/Netease/MuMuPlayer/Contents/MacOS/adb"),
            ("Nox App Player (macOS)", "/Applications/NoxAppPlayer.app", "/Applications/NoxAppPlayer.app/Contents/MacOS/adb"),
            ("LDPlayer (macOS)", "/Applications/LDPlayer.app", "/Applications/LDPlayer.app/Contents/MacOS/adb"),
        ]

        found = []
        for name, app_path, adb_path in known_apps:
            if os.path.exists(app_path):
                adb_exists = os.path.exists(adb_path) and (sys.platform == "win32" or os.access(adb_path, os.X_OK))
                found.append({
                    "name": name,
                    "app_path": app_path,
                    "adb_path": adb_path if adb_exists else "未找到專用 adb",
                    "status": "已安裝 (附帶 ADB)" if adb_exists else "已安裝 (無內建 ADB)"
                })
        return found

    @staticmethod
    def run_full_diagnosis(bot_instance=None) -> Dict[str, Any]:
        """執行全方位診斷並產出結構化診斷報告"""
        diag = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "os_info": f"{platform.system()} {platform.release()} ({platform.machine()})",
            "python_executable": sys.executable,
            "python_version": sys.version.split()[0],
            "port_5037_open": SystemDiagnostics.check_port("127.0.0.1", 5037),
            "emulators": SystemDiagnostics.get_installed_emulators(),
            "library_versions": {},
            "adb_devices": [],
            "screencap_test": "未測試",
            "ocr_engine_test": "未測試",
            "warnings_and_advice": []
        }

        # 1. 檢查關鍵依賴庫版本
        libs = ["ppadb", "cv2", "numpy", "rapidocr_onnxruntime", "PIL"]
        for lib in libs:
            try:
                mod = __import__(lib)
                ver = getattr(mod, "__version__", "已安裝 (無版本資訊)")
                diag["library_versions"][lib] = ver
            except Exception as e:
                diag["library_versions"][lib] = f"MISSING ({e})"
                diag["warnings_and_advice"].append(f"關鍵套件 {lib} 缺少或損毀，請執行 pip install 安裝。")

        # 2. 檢查 ADB 裝置清單
        try:
            from ppadb.client import Client as AdbClient
            client = AdbClient(host="127.0.0.1", port=5037)
            devices = client.devices()
            diag["adb_devices"] = [d.serial for d in devices]
            if not devices:
                diag["warnings_and_advice"].append("ADB Server 正在運行但未發現裝置。請確認模擬器已完全開機進入 Android 系統。")
        except Exception as e:
            diag["adb_devices"] = f"無法連線 5037 ({e})"
            diag["warnings_and_advice"].append("無法連線本機 5037 埠，請確認 ADB Server 是否已啟動。")

        # 3. 測試截圖與 OCR
        if bot_instance and getattr(bot_instance, "device", None):
            try:
                screen = bot_instance.capture_screen()
                if screen is not None:
                    h, w = screen.shape[:2]
                    diag["screencap_test"] = f"正常 (解析度: {w}x{h})"
                    # 測試 OCR
                    ocr_res = bot_instance.scan_text(screen)
                    diag["ocr_engine_test"] = f"正常 (畫面偵測到 {len(ocr_res)} 處文字)"
                else:
                    diag["screencap_test"] = "失敗 (screencap 回傳空資料)"
            except Exception as e:
                diag["screencap_test"] = f"異常: {e}"
        else:
            diag["screencap_test"] = "未連線裝置，略過截圖測試"

        return diag

    @staticmethod
    def format_report_for_clipboard(diag: Dict[str, Any], recent_logs: str = "") -> str:
        """格式化為整潔 Markdown，方便使用者一鍵複製貼上發問"""
        lines = []
        lines.append("```markdown")
        lines.append("=== 【棒球手遊自動腳本】一鍵系統自檢與錯誤診斷報告 ===")
        lines.append(f"• 檢查時間: {diag['timestamp']}")
        lines.append(f"• 作業系統: {diag['os_info']}")
        lines.append(f"• Python 路徑: {diag['python_executable']} (v{diag['python_version']})")
        lines.append(f"• ADB 服務埠 (5037): {'🟢 正常開啟' if diag['port_5037_open'] else '🔴 未開啟'}")
        lines.append("")
        lines.append("【模擬器安裝掃描】:")
        if diag["emulators"]:
            for emu in diag["emulators"]:
                lines.append(f"  - {emu['name']}: {emu['status']} ({emu['app_path']})")
        else:
            lines.append("  - ⚠️ 未偵測到預設路徑中的常見模擬器")

        lines.append("")
        lines.append("【ADB 已連線裝置】:")
        if isinstance(diag["adb_devices"], list):
            if diag["adb_devices"]:
                lines.append(f"  - 🟢 偵測到裝置: {', '.join(diag['adb_devices'])}")
            else:
                lines.append("  - 🟡 目前連線清單為空 (尚未連接裝置)")
        else:
            lines.append(f"  - 🔴 {diag['adb_devices']}")

        lines.append("")
        lines.append("【依賴庫狀態】:")
        for k, v in diag["library_versions"].items():
            lines.append(f"  - {k}: {v}")

        lines.append("")
        lines.append(f"【螢幕擷取測試】: {diag['screencap_test']}")
        lines.append(f"【OCR 辨識測試】: {diag['ocr_engine_test']}")

        if diag["warnings_and_advice"]:
            lines.append("")
            lines.append("【⚠️ 自檢警告與建議】:")
            for w in diag["warnings_and_advice"]:
                lines.append(f"  ! {w}")

        if recent_logs.strip():
            lines.append("")
            lines.append("【最近 25 行日誌】:")
            lines.append("--------------------------------------------------")
            lines.append(recent_logs.strip())
            lines.append("--------------------------------------------------")

        lines.append("==================================================")
        lines.append("```")
        return "\n".join(lines)
