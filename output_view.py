import sublime, sublime_plugin
import queue, threading, time

outputViewPanel = None

def AppendStrToPanel(panel, strData):
	panel.run_command("append", {"characters": strData})
	
class OutputView:
	def __init__(self):
		self.queue = queue.Queue()
		self.gotDataEvent = threading.Event()
		self.pollThread = threading.Thread(target = self.Poll)
		self.pollThread.daemon = True
		self.pollThread.start()		
	
	def Show(self):
		window = sublime.active_window()
		window.run_command("output_view")

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

			AppendStrToPanel(outputViewPanel, res)
			time.sleep(0.05)

	def ToggleShow(self):
		self.Show()

class OutputViewCommand(sublime_plugin.WindowCommand):
	def __init__(self, window):
		global outputViewPanel
		outputViewPanel = window.create_output_panel("FuseOutput")
		outputViewPanel.set_name("Fuse - Output")
		self.window = window

	def run(self):
		window = self.window	
		window.run_command("show_panel", {"panel": "output.FuseOutput", "toggle": True })