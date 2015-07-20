import sublime, sublime_plugin

def gotoDefinition(data):
	window = sublime.active_window()
	path = data["Path"]
	
	caretPos = data["CaretPosition"]
	line = int(caretPos["Line"])
	column = int(caretPos["Character"])
	openCommand = data["Path"] + ":" + str(line) + ":" + str(column)

	view = window.open_file(openCommand, sublime.ENCODED_POSITION | sublime.TRANSIENT)