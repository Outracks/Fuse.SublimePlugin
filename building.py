import subprocess
import threading
import os
import sublime

from .fuse_util import getFusePathFromSettings
from .log import log

class BuildInstance(threading.Thread):
	def __init__(self, cmd, title, fuseNotFoundHandler):
		threading.Thread.__init__(self)
		self.cmd = cmd
		self.daemon = True
		self.output = OutputView(title)
		self.fuseNotFoundHandler = fuseNotFoundHandler
		self.process = None

	def run(self):
		log().info("-- Opening subprocess %s", str(self.cmd))
		try:
			if os.name == "nt":
				CREATE_NO_WINDOW = 0x08000000
				self.process = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=CREATE_NO_WINDOW)
			else:
				self.process = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		except:
			self.fuseNotFoundHandler()
			self.output.close()
			return
		for line in iter(self.process.stdout.readline,b''):
			self.output.append(line.decode("utf-8"))
		self.process.wait()

	def stop(self):
		if self.process:
			try:
				self.process.kill()
			except ProcessLookupError:
				pass #It died by itself, which is fine
		self.output.close()

class OutputView:
	def __init__(self, title):
		self.title = title
		window = sublime.active_window()
		self.view = window.new_file()
		self.view.set_scratch(True)
		self.view.set_name(title)

	def append(self, line):
		self.view.run_command("append", {"characters": line})

	def close(self):
		try:
			window = self.view.window()
			groupIndex, viewIndex = window.get_view_index(self.view)
			window.run_command("close_by_index", { "group": groupIndex, "index": viewIndex })
		except:
			pass #Failing to close a tab is not critical

class BuildManager:
	def __init__(self, fuseNotFoundHandler):
		self.builds = {}
		self.fuseNotFoundHandler = fuseNotFoundHandler

	def preview(self, target, path):
		fusePath = getFusePathFromSettings()
		start_preview = [fusePath, "preview", "--target=" + target, "--name=Sublime_Text_3", path]
		name = target.capitalize() + " Preview"
		self.__start(target, start_preview, name)

	def build(self, target):
		self.__start(target, [], target.capitalize() + " Build")

	def __start(self, target, cmd, name):
		if name in self.builds:
			self.builds[name].stop()
		build = BuildInstance(cmd, name, self.fuseNotFoundHandler)
		self.builds[name] = build
		build.start()
