"""
圖像辨識遊戲運行腳本 - 啟動入口

    python3 main.py          啟動圖形介面（預設）
    python3 main.py --cli    不開介面，直接以預設步驟執行循序腳本
    python3 main.py --fast   啟動極簡高速反應式腳本
    python3 main.py --version 顯示版本
"""
import sys


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg in ("--version", "-V"):
        import version
        print(f"{version.APP_NAME} v{version.VERSION}")
    elif arg == "--cli":
        from core.bot import GameBot
        bot = GameBot()
        if bot.connect():
            bot.run_loop()
        else:
            print("連線失敗。")
    elif arg == "--fast":
        from core.fast_bot import FastReactiveBot
        FastReactiveBot().run()
    else:
        from ui.app import main as run_gui
        run_gui()


if __name__ == "__main__":
    main()
