import sublime, sublime_plugin
import queue, threading, time

buildOutPanels = []
windowsWithPanel = []

def AppendStrToPanel(panel, strData):
	panel.run_command("append", {"characters": strData})
	
class BuildOutputView:
	def __init__(self):
		self.queue = queue.Queue()
		self.gotDataEvent = threading.Event()
		self.pollThread = threading.Thread(target = self.Poll)
		self.pollThread.daemon = True
		self.pollThread.start()		

	def Show(self):
		window = sublime.active_window()
		window.run_command("build_output")
		
	def Write(self, strData):
		self.queue.put(strData, True)
		self.gotDataEvent.set()		

	def Poll(self):
		while(True):
			self.gotDataEvent.wait()
			self.gotDataEvent.clear()
			res = ""
			while not self.queue.empty():
				res += self.queue.get_nowait()

			for panel in buildOutPanels:
				AppendStrToPanel(panel, res)
			
			time.sleep(0.05)

	def ToggleShow(self):
		self.Show()		

class BuildOutputCommand(sublime_plugin.WindowCommand):
	def __init__(self, window):
		if window not in windowsWithPanel:
			windowsWithPanel.append(window)

			buildOutPanel = window.create_output_panel("FuseBuildOutput")
			buildOutPanel.set_name("Fuse - Build Output")
			buildOutPanels.append(buildOutPanel)

		self.window = window

	def run(self):
		window = self.window	
		window.run_command("show_panel", {"panel": "output.FuseBuildOutput", "toggle": True})		