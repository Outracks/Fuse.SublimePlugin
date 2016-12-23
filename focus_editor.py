import os
import sublime
import subprocess

from .log import log

class FocusEditorService:

	def __init__(self, msgManager, interop):
		self.msgManager = msgManager
		self.interop = interop

	def publish(self):
		self.msgManager.sendRequestAsync(
			self.interop,
			"PublishService",
			{
			"RequestNames" : ["FocusEditor"]
			},
			self.focusEditorServiceSuccess)

	def focusEditorServiceSuccess(self, _):
		log().info("Successfully registered FocusEditor service")

	def tryHandle(self, request):
		if request.name != "FocusEditor":
			return False
		fileName = request.arguments["File"]
		line = request.arguments["Line"]
		column = request.arguments["Column"]
		if not os.path.isfile(fileName):
			self._returnFailure("File '{}' does not exist".format(fileName), request.id)
			return True
		window = self._tryGetWindowFor(request.arguments["Project"])
		if window:
			try:
				window.open_file( "{}:{}:{}".format(fileName, line, column), sublime.ENCODED_POSITION)
				if sublime.platform() == "osx":
					self._focusWindowOSX()
					self.msgManager.sendResponse(self.interop, request.id, "Success")
					return True
				elif sublime.platform() == "windows":
					self.msgManager.sendResponse(self.interop, request.id, "Success", {"FocusHwnd":window.hwnd()})
					return True
			except Exception as e:
				self._returnFailure(str(e), request.id)
				return True
		return False

	def _returnFailure(self, msg, id):
		log().info("FocusEditorService: " + msg)
		self.msgManager.sendResponse(self.interop, id, "Error", {}, [{"Code":2, "Message": msg}])

	def _tryGetWindowFor(self, project):
		if not os.path.isfile(project):
			return None
		for window in sublime.windows():
			for folder in window.folders():
				if project.startswith(folder):
					return window
		return None

	def _focusWindowOSX(self):
		cmd = """
			tell application "System Events"
				activate application "Sublime Text"
			end tell"""
		proc = subprocess.Popen(['/usr/bin/osascript', "-e", cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		stdout = stderr = ""
		try:
			stdoout, stderr = proc.communicate(timeout=2)
		except TimeoutExpired:
			proc.kill()
			stdoout, stderr = proc.communicate()
		if proc.returncode != 0:
			log().info("Failed to focus window via osaxcript: '" + str(stdout) + "', '" + str(stderr) + "'")
