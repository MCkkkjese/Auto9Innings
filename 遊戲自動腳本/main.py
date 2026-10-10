"""
棒球手遊自動化腳本 - 啟動入口 
預設啟動現代化 CustomTkinter 控制面板介面 (gui.py)。
"""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from bot_core import BaseballBot
        bot = BaseballBot()
        if bot.connect():
            bot.load_templates()
            bot.run_loop()
        else:
            print("連線失敗。")
    elif len(sys.argv) > 1 and sys.argv[1] == "--fast":
        # 啟動極簡高速反應式刷關腳本
        from fast_bot import FastReactiveBot
        bot = FastReactiveBot()
        bot.run()
    else:
        # 預設啟動：現代化 CustomTkinter 圖形化介面 (GUI)
        from gui import main
        main()
