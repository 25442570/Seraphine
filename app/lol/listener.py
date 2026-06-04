import subprocess
import logging
import json
import os

import asyncio
from PyQt5.QtCore import QThread, pyqtSignal
import aiohttp

from app.common.logger import logger
from app.common.signals import signalBus
from app.common.util import getLolClientPids, isLolGameProcessExist, getTasklistPath

TAG = "Listener"


class LolProcessExistenceListener(QThread):
    def __init__(self, parent):
        # 当前 Seraphine 连接的客户端 pid
        self.runningPid = 0
        self._is_running = True  # 添加运行标志

        super().__init__(parent)

    def stop(self):
        """安全停止线程"""
        self._is_running = False
        self.wait()

    def run(self):
        path = getTasklistPath()

        if not path:
            signalBus.tasklistNotFound.emit()
            return

        while self._is_running:  # 使用运行标志替代无限循环
            try:
                # 检查是否系统正在关闭
                if os.name == 'nt':
                    try:
                        import win32api
                        # 简单检查 - 如果调用失败，可能是系统正在关闭
                        win32api.GetTickCount()
                    except:
                        logger.info("System may be shutting down, stopping listener", TAG)
                        break

                # 取一下当前运行中的所有客户端 pid
                pids = getLolClientPids(path)

                # 如果有客户端正在运行
                if len(pids) != 0:

                    # 如果当前没有连接客户端，则是第一个客户端启动了
                    if self.runningPid == 0:
                        self.runningPid = pids[0]
                        signalBus.lolClientStarted.emit(self.runningPid)

                    # 如果当前有客户端启动中，但是当前连接的客户端不在这些客户端里
                    # 则说明是原来多开了客户端，现在原本连接的客户端关了，则切换到新的客户端
                    elif self.runningPid not in pids:
                        self.runningPid = pids[0]
                        signalBus.lolClientChanged.emit(self.runningPid)

                # 如果没有任何客户端在运行，且上一次检查时有客户端在运行
                else:
                    if self.runningPid and not isLolGameProcessExist(path):
                        self.runningPid = 0
                        signalBus.lolClientEnded.emit()

            except Exception as e:
                # 捕获所有异常，避免线程在系统关闭时崩溃
                if self._is_running:  # 只有在正常运行时才记录
                    logger.warning(f"Listener error (may be system shutdown): {e}", TAG)
                else:
                    break

            # 使用可中断的等待
            if self._is_running:
                self.msleep(1500)


class StoppableThread(QThread):
    def __init__(self, target, parent) -> None:
        self.target = target
        self._is_running = True
        super().__init__(parent)

    def stop(self):
        """安全停止线程"""
        self._is_running = False
        self.wait()

    def run(self):
        try:
            self.target()
        except Exception as e:
            # 捕获异常避免在系统关闭时崩溃
            logger.warning(f"StoppableThread error: {e}", TAG)
