#!/usr/bin/env python
# Copyright (C) 2007-2010,	Valek Filippov (frob@df.ru)
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of version 3 or later of the GNU General Public
# License as published by the Free Software Foundation.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301
# USA


import sys,struct
import gobject
import gtk
import tree
import hexdump
import Doc
import oleparse
import escher
import vsdchunks,vsdstream4
import emfparse,svm,mf

version = "0.5.19"

ui_info = \
'''<ui>
	<menubar name='MenuBar'>
	<menu action='FileMenu'>
		<menuitem action='New'/>
		<menuitem action='Open'/>
		<menuitem action='Save'/>
		<menuitem action='Close'/>
		<separator/>
		<menuitem action='Quit'/>
	</menu>
	<menu action='EditMenu'>
		<menuitem action='Insert'/>
		<menuitem action='More'/>
		<menuitem action='Less'/>
	</menu>
	<menu action='ViewMenu'>
	</menu>
	<menu action='HelpMenu'>
		<menuitem action='About'/>
	</menu>
	</menubar>
</ui>'''

ui_popup = \
'''<ui>
	<popup name="EntryPopup">
		<menuitem name="child" action="child"/>
	</popup>
</ui>'''

def register_stock_icons():
	''' This function registers our custom toolbar icons, so they  can be themed. '''
	# Add our custom icon factory to the list of defaults
	factory = gtk.IconFactory()
	factory.add_default()

class ApplicationMainWindow(gtk.Window):
	def __init__(self, parent=None):
		register_stock_icons()
		# Create the toplevel window
		gtk.Window.__init__(self)
		try:
			self.set_screen(parent.get_screen())
		except AttributeError:
			self.connect('destroy', lambda *w: gtk.main_quit())

		self.set_title("OLE toy")
		self.set_default_size(400, 350)

		merge = gtk.UIManager()
		self.set_data("ui-manager", merge)
		merge.insert_action_group(self.__create_action_group(), 0)
		self.add_accel_group(merge.get_accel_group())

		try:
			mergeid = merge.add_ui_from_string(ui_info)
		except gobject.GError, msg:
			print "building menus failed: %s" % msg
		bar = merge.get_widget("/MenuBar")
		bar.show()

		table = gtk.Table(1, 3, False)
		self.add(table)

		table.attach(bar,
			# X direction #		  # Y direction
			0, 1,					  0, 1,
			gtk.EXPAND | gtk.FILL,	 0,
			0,						 0);
		
		self.notebook =gtk.Notebook()
		self.notebook.set_tab_pos(gtk.POS_BOTTOM)
		table.attach(self.notebook,
			# X direction #		  # Y direction
			0, 1,					  1, 2,
			gtk.EXPAND | gtk.FILL,	 gtk.EXPAND | gtk.FILL,
			0,						 0);

		# Create statusbar
		self.statusbar = gtk.HBox()
		self.entry = gtk.Entry()
		self.statusbar.pack_start(self.entry, False,False,2)
		self.entry.connect ("activate",self.on_entry_activate)
		self.label = gtk.Label()
		self.label.set_use_markup(True)
		self.statusbar.pack_start(self.label, True,True,2)
		
		table.attach(self.statusbar,
			# X direction		   Y direction
			0, 1,				   2, 3,
			gtk.EXPAND | gtk.FILL,  0,
			0,					  0)
		self.show_all()
		self.das = {}
		self.fname = ''
		self.selection = None

		self.dictmod, self.dictview = mf.emf_gentree()
		self.dictview.connect("row-activated", self.on_dict_row_activated)


		if len(sys.argv) > 1:
			for i in range(len(sys.argv)-1):
				self.fname = sys.argv[i+1]
				self.activate_open()

	def __create_action_group(self):
		# GtkActionEntry
		entries = (
			( "FileMenu", None, "_File" ),			   # name, stock id, label
			( "EditMenu", None, "_Edit" ),			   # name, stock id, label
			( "ViewMenu", None, "_View" ),			   # name, stock id, label
			( "HelpMenu", None, "_Help" ),			   # name, stock id, label
			( "Insert", gtk.STOCK_ADD,					# name, stock id
				"Insert _Record","<control>R",					  # label, accelerator
				"Insert EMF Record after the current one",							 # tooltip
				self.activate_add),
			( "More", gtk.STOCK_ADD,					# name, stock id
				"_More bytes","<control>M",					  # label, accelerator
				"Add more bytes at the end of the current record",							 # tooltip
				self.activate_more),
			( "Less", gtk.STOCK_ADD,					# name, stock id
				"_Less bytes","<control>L",					  # label, accelerator
				"Remove some bytes at the end of the current record",							 # tooltip
				self.activate_less),
			( "New", gtk.STOCK_NEW,					# name, stock id
				"_New","<control>N",					  # label, accelerator
				"Create file",							 # tooltip
				self.activate_new),
			( "Open", gtk.STOCK_OPEN,					# name, stock id
				"_Open","<control>O",					  # label, accelerator
				"Open a file",							 # tooltip
				self.activate_open),
			( "Save", gtk.STOCK_SAVE,                    # name, stock id
				"_Save","<control>S",                      # label, accelerator
				"Save the file",                             # tooltip
				self.activate_save),
			( "Close", gtk.STOCK_CLOSE,                    # name, stock id
				"Close","<control>Z",                      # label, accelerator
				"Close the file",                             # tooltip
				self.activate_close),
			( "Quit", gtk.STOCK_QUIT,					# name, stock id
				"_Quit", "<control>Q",					 # label, accelerator
				"Quit",									# tooltip
				self.activate_quit ),

			( "About", None,							 # name, stock id
				"_About", "<control>A",					# label, accelerator
				"About",								   # tooltip
				self.activate_about ),
		);

		# Create the menubar and toolbar
		action_group = gtk.ActionGroup("AppWindowActions")
		action_group.add_actions(entries)
		return action_group

	def activate_add (self, action):
		pn = self.notebook.get_current_page()
		if pn != -1:
			window = gtk.Window(gtk.WINDOW_TOPLEVEL)
			window.set_resizable(True)
			window.set_default_size(650, 700)
			window.set_border_width(0)
			viewscroll = gtk.ScrolledWindow()
			viewscroll.set_policy(gtk.POLICY_AUTOMATIC,gtk.POLICY_AUTOMATIC)
			viewscroll.add(self.dictview)
			window.set_title("Add record: "+self.das[pn].pname)
			window.add(viewscroll)
			window.show_all()
		return

	def activate_more (self, action):
		pn = self.notebook.get_current_page()
		treeSelection = self.das[pn].view.get_selection()
		model, iter1 = treeSelection.get_selected()
		size = model.get_value(iter1,2)
		value = model.get_value(iter1,3)
		model.set_value(iter1,2,size+4)
		model.set_value(iter1,3,value+'\x00'*4)


	def activate_less (self, action):
		pn = self.notebook.get_current_page()
		treeSelection = self.das[pn].view.get_selection()
		model, iter1 = treeSelection.get_selected()
		size = model.get_value(iter1,2)
		value = model.get_value(iter1,3)
		if size > 12:
			model.set_value(iter1,2,size-4)
			model.set_value(iter1,3,value[0:size-12])

	def on_dict_row_activated(self, view, path, column):
		pn = self.notebook.get_current_page()
		model = self.das[pn].view.get_model()
		dictmodel = self.dictview.get_model()
		treeSelection = self.das[pn].view.get_selection()
		model2, iter2 = treeSelection.get_selected()
#		print "Where? ",model2.get_string_from_iter(iter2)
		iter = dictmodel.get_iter(path)
		type = dictmodel.get_value(iter,1)
		if type != -1:
			size = int(dictmodel.get_value(iter,2))
			rname = mf.emr_ids[type]
			if iter2:
				iter1 = model.insert_after(None,iter2)
			else:
				iter1 = model.append(None,None)
			model.set_value(iter1,0,rname)
			model.set_value(iter1,1,("emf",type))
			model.set_value(iter1,2,size)
			model.set_value(iter1,3,struct.pack("<I",type)+struct.pack("<I",size)+"\x00"*(size-8))
			model.set_value(iter1,6,model.get_string_from_iter(iter1))
			print "Insert:",rname,size


	def activate_save (self, action):
		pn = self.notebook.get_current_page()
		ftype = self.das[pn].type
		if  ftype == "WMF" or ftype  == "APWMF" or ftype  == "EMF" or ftype == "SVM":
			fname = self.file_open('Save',None,gtk.FILE_CHOOSER_ACTION_SAVE)
			if fname:
				mf.mf_save(self.das[pn],fname,ftype)
		else:
			print '"Save" is not implemented for non-MF'

	def activate_about(self, action):
		dialog = gtk.AboutDialog()
		dialog.set_name("OLE toy v"+version)
		dialog.set_copyright("\302\251 Copyright 2010-2011 V.F.")
		dialog.set_website("http://www.gnome.ru/")
		## Close dialog on user response
		dialog.connect ("response", lambda d, r: d.destroy())
		dialog.show()

	def activate_quit(self, action):
		 gtk.main_quit()
		 return
 
	def update_statusbar(self, buffer):
		self.label.set_markup("%s"%buffer)

	def on_entry_activate (self,action):
		goto = self.entry.get_text()
		pn = self.notebook.get_current_page()
		col = self.das[pn].view.get_column(0)
		try:
			self.das[pn].view.expand_to_path(goto)
			self.das[pn].view.set_cursor_on_cell(goto)
		except:
			print "No such path"

	def activate_close(self, action):
		pn = self.notebook.get_current_page()
		if pn == -1:
			gtk.main_quit()
		else:
			del self.das[pn]         
			self.notebook.remove_page(pn)
			if pn < len(self.das):  ## not the last page
				for i in range(pn,len(self.das)):
					self.das[i] = self.das[i+1]
				del self.das[len(self.das)-1]
		return

	def on_row_keypressed (self, view, event):
		treeSelection = view.get_selection()
		model, iter1 = treeSelection.get_selected()
		if iter1:
			intPath = model.get_path(iter1)
			if event.keyval == 65535:
				model.remove(iter1)
				if model.get_iter_first():
					if intPath >= 0:
						view.set_cursor(intPath)
						view.grab_focus()
			else:
				if event.keyval == 99 and event.state == gtk.gdk.CONTROL_MASK:
					self.selection = (model.get_value(iter1,0),model.get_value(iter1,1),model.get_value(iter1,2),model.get_value(iter1,3))
				if event.keyval == 118 and event.state == gtk.gdk.CONTROL_MASK and self.selection != None:
					niter = model.insert_after (None, iter1)
					model.set_value (niter, 0, self.selection[0])
					model.set_value (niter, 1, self.selection[1])
					model.set_value (niter, 2, self.selection[2])
					model.set_value (niter, 3, self.selection[3])

	def on_row_keyreleased (self, view, event):
		treeSelection = view.get_selection()
		model, iter1 = treeSelection.get_selected()
		if iter1:
			intPath = model.get_path(iter1)
			self.on_row_activated(view, intPath, 0)
			if event.type  == gtk.gdk.BUTTON_RELEASE and event.button == 3:
				self.entry.set_text(model.get_string_from_iter(iter1))

	def on_hdrow_keyreleased (self, view, event):
		treeSelection = view.get_selection()
		model, iter1 = treeSelection.get_selected()
		if iter1:
			intPath = model.get_path(iter1)
			self.on_hdrow_activated(view, intPath, 0)

	def on_hdrow_activated(self, view, path, column):
		pn = self.notebook.get_current_page()
		model = self.das[pn].hd.hdview.get_model()
		hd = self.das[pn].hd
		iter1 = model.get_iter(path)
		offset = model.get_value(iter1,2)
		size = model.get_value(iter1,3)
		buffer_hex = hd.txtdump_hex.get_buffer()
		try:
			tag = buffer_hex.create_tag("hl",background="yellow")
		except:
			pass
		buffer_hex.remove_tag_by_name("hl",buffer_hex.get_iter_at_offset(0),buffer_hex.get_iter_at_offset(buffer_hex.get_char_count()))
		iter_hex = buffer_hex.get_iter_at_offset(offset*3)
		vadj = hd.vscroll2.get_vadjustment()
		newval = vadj.get_upper()/buffer_hex.get_line_count()*(offset/16 -1)
		lim = vadj.get_upper() - hd.vscroll2.allocation[3]
		if newval < lim:
			vadj.set_value(newval)
		else:
			vadj.set_value(lim)
		off2 = offset*3+size*3-1
		if off2 < 0:
			off2 = 0
		iter_hex_end = buffer_hex.get_iter_at_offset(off2)
		buffer_hex.apply_tag_by_name("hl",iter_hex,iter_hex_end)

	def edited_cb (self, cell, path, new_text):
		pn = self.notebook.get_current_page()
		treeSelection = self.das[pn].view.get_selection()
		model, iter1 = treeSelection.get_selected()
		hd = self.das[pn].hd
		value = model.get_value(iter1,3) 
		hditer = hd.hdmodel.get_iter(path)

		offset = hd.hdmodel.get_value(hditer,2)
		size = hd.hdmodel.get_value(hditer,3)
		fmt = hd.hdmodel.get_value(hditer,4)
#		print 'Format: ', fmt

		if fmt == "clr":
			value = value[0:offset] + struct.pack("B",int(new_text[4:6],16))+struct.pack("B",int(new_text[2:4],16))+struct.pack("B",int(new_text[0:2],16))+value[offset+3:]
		else:
			if fmt == "txt":
				value = value[0:offset]+new_text+value[offset+size:]
			else:
				value = value[0:offset] + struct.pack(fmt,float(new_text))+value[offset+size:]

		model.set_value(iter1,3,value)
		self.on_row_activated(self.das[pn].view,model.get_path(iter1),0)
		hd.hdview.set_cursor(path)
		hd.hdview.grab_focus()

	def on_row_activated(self, view, path, column):
		pn = self.notebook.get_current_page()
		model = self.das[pn].view.get_model()
		hd = self.das[pn].hd
		iter1 = model.get_iter(path)
		ntype = model.get_value(iter1,1)
#		print "NType: %s %02x"%(ntype[0],ntype[1])
		size = model.get_value(iter1,2)
		data = model.get_value(iter1,3)
		hd.data = data
		str_addr = ''
		str_hex = ''
		str_asc = ''
		if data != None:
			for line in range(0, len(data), 16):
				str_addr+="%07x: "%line
				end = min(16, len(data) - line)
				for byte in range(0, 15):
					if byte < end:
						str_hex+="%02x " % ord(data[line + byte])
						if ord(data[line + byte]) < 32 or 126<ord(data[line + byte]):
							str_asc +='.'
						else:
							str_asc += data[line + byte]
				if end > 15:			
					str_hex+="%02x" % ord(data[line + 15])
					if ord(data[line + 15]) < 32 or 126<ord(data[line + 15]):
						str_asc += '.'
					else:
						str_asc += data[line + 15]
					str_hex+='\n'
					str_asc+='\n'
					str_addr+='\n'
			if len(str_hex) < 47:
				str_hex += " "*(47-len(str_hex))
	
			buffer_addr = hd.txtdump_addr.get_buffer()
			iter_addr = buffer_addr.get_iter_at_offset(0)
			iter_addr_end = buffer_addr.get_iter_at_offset(buffer_addr.get_char_count())
			buffer_addr.delete(iter_addr, iter_addr_end)
			buffer_addr.insert_with_tags_by_name(iter_addr, str_addr,"monospace")
			buffer_asc = hd.txtdump_asc.get_buffer()
			iter_asc = buffer_asc.get_iter_at_offset(0)
			iter_asc_end = buffer_asc.get_iter_at_offset(buffer_asc.get_char_count())
			buffer_hex = hd.txtdump_hex.get_buffer()
			iter_hex = buffer_hex.get_iter_at_offset(0)
			iter_hex_end = buffer_hex.get_iter_at_offset(buffer_hex.get_char_count())
			buffer_hex.delete(iter_hex, iter_hex_end)
			buffer_hex.insert_with_tags_by_name(iter_hex, str_hex,"monospace")
			buffer_asc.delete(iter_asc, iter_asc_end)
			buffer_asc.insert_with_tags_by_name(iter_asc, str_asc,"monospace")
	
			hd.hdmodel.clear()
			if ntype != 0:
				if ntype[0] == "escher":
					if ntype[1] == "odraw":
						if escher.odraw_ids.has_key(ntype[2]):
							escher.odraw_ids[ntype[2]](hd, size, data)
				elif ntype[0] == "vsd":
					if ntype[1] == "chnk":
						if vsdchunks.chnk_func.has_key(ntype[2]):
							vsdchunks.chnk_func[ntype[2]](hd, size, data)
					if ntype[1] == "str4":
						if vsdstream4.stream_func.has_key(ntype[2]):
							vsdstream4.stream_func[ntype[2]](hd, size, data)
				elif ntype[0] == "emf":
					if emfparse.emr_ids.has_key(ntype[1]):
						emfparse.emr_ids[ntype[1]](hd,size,data)
				elif ntype[0] == "wmf":
					if emfparse.wmr_ids.has_key(ntype[1]):
						emfparse.wmr_ids[ntype[1]](hd,size,data)
				elif ntype[0] == "svm":
					if svm.svm_ids.has_key(ntype[1]):
						svm.svm_ids[ntype[1]](hd,size,data)
				elif ntype[2] == 0xff:
					iter1 = hd.hdmodel.append(None, None)
					hd.hdmodel.set (iter1, 0, "Txt:", 1, unicode(data,"utf-16"),2,0,3,len(data),4,"txt")


	def hdselect_cb(self,event,udata):
		pn = self.notebook.get_current_page()
		model = self.das[pn].view.get_model()
		type = self.das[pn].type
		#print "Type: ",type
		hd = self.das[pn].hd
		try:
			start,end = hd.txtdump_hex.get_buffer().get_selection_bounds()
		except:
			return
		buffer_asc = hd.txtdump_asc.get_buffer()

		slo = start.get_offset()
		elo = end.get_offset()
		if slo%3 == 1:
			slo -= 1
			start.set_offset(slo)
		if slo%3 == 2:
			slo += 1
			start.set_offset(slo)
		if elo%3 == 0:
			elo -= 1
			end.set_offset(elo)
		if elo%3 == 1:
			elo += 1
			end.set_offset(elo)
		hd.txtdump_hex.get_buffer().move_mark_by_name ('selection_bound',start)
		hd.txtdump_hex.get_buffer().move_mark_by_name ('insert',end)

		asl = start.get_line()
		ael = end.get_line()
		aslo = start.get_line_offset()
		aelo = end.get_line_offset()

		try:
			tag = buffer_asc.create_tag("hl",background="yellow")
		except:
			pass
		buffer_asc.remove_tag_by_name("hl",buffer_asc.get_iter_at_offset(0),buffer_asc.get_iter_at_offset(buffer_asc.get_char_count()))
		iter_asc = buffer_asc.get_iter_at_offset(asl*17+aslo/3)
		iter_asc_end = buffer_asc.get_iter_at_offset(ael*17+aelo/3+1)
		buffer_asc.apply_tag_by_name("hl",iter_asc,iter_asc_end)
		dstart = asl*16+aslo/3
		dend = ael*16+aelo/3+1
		buf = hd.data[dstart:dend]
		if len(buf) == 2:
			txt = "LE: %s\tBE: %s"%(struct.unpack("<h",buf)[0],struct.unpack(">h",buf)[0])
			self.update_statusbar(txt)
		if len(buf) == 4:
			txt = "LE: %s\tBE: %s"%(struct.unpack("<i",buf)[0],struct.unpack(">i",buf)[0])
			if type == "PUB":
				txt += "\t%s"%struct.unpack("<i",buf)[0]/12700.
			self.update_statusbar(txt)
		if len(buf) == 8:
			txt = "LE: %s\tBE: %s"%(struct.unpack("<d",buf)[0],struct.unpack(">d",buf)[0])
			self.update_statusbar(txt)
		if len(buf) == 3:
			txt = '<span background="#%02x%02x%02x">RGB</span>  '%(ord(buf[0]),ord(buf[1]),ord(buf[2]))
			txt += '<span background="#%02x%02x%02x">BGR</span>'%(ord(buf[2]),ord(buf[1]),ord(buf[0]))

			self.update_statusbar(txt)


	def activate_new (self,parent=None):
		doc = Doc.Page()
		dnum = len(self.das)
		self.das[dnum] = doc
		scrolled = doc.scrolled
		doc.hd = hexdump.hexdump()
		doc.hd.txtdump_hex.connect('populate_popup',self.build_context_menu)
		vpaned = doc.hd.vpaned
		hpaned = gtk.HPaned()
		hpaned.add1(scrolled)
		hpaned.add2(vpaned)
		label = gtk.Label("Unnamed")
		self.notebook.append_page(hpaned, label)
		self.notebook.show_tabs = True
		self.notebook.show_all()
		doc.view.connect("row-activated", self.on_row_activated)
		doc.view.connect("key-press-event", self.on_row_keypressed)
		doc.view.connect("key-release-event", self.on_row_keyreleased)
		doc.view.connect("button-release-event", self.on_row_keyreleased)
		doc.hd.hdview.connect("row-activated", self.on_hdrow_activated)
		doc.hd.hdview.connect("key-release-event", self.on_hdrow_keyreleased)
		doc.hd.hdview.connect("button-release-event", self.on_hdrow_keyreleased)



	def activate_open(self,parent=None):
		if self.fname !='':
			fname = self.fname
			self.fname = ''
		else:
			fname = self.file_open()
		print fname
		if fname:
			doc = Doc.Page()
			doc.fname = fname
			doc.hd = hexdump.hexdump()
			err = doc.fload()
			if err == 0:
				dnum = len(self.das)
				self.das[dnum] = doc
				scrolled = doc.scrolled
				vpaned = doc.hd.vpaned
				doc.view.connect("row-activated", self.on_row_activated)
				doc.view.connect("key-press-event", self.on_row_keypressed)
				doc.view.connect("key-release-event", self.on_row_keyreleased)
				doc.view.connect("button-release-event", self.on_row_keyreleased)
				doc.hd.hdview.connect("row-activated", self.on_hdrow_activated)
				doc.hd.hdview.connect("key-release-event", self.on_hdrow_keyreleased)
				doc.hd.hdview.connect("button-release-event", self.on_hdrow_keyreleased)
				doc.hd.hdrend.connect('edited', self.edited_cb)
				doc.hd.txtdump_hex.connect('button-release-event',self.hdselect_cb) 
				hpaned = gtk.HPaned()
				hpaned.add1(scrolled)
				hpaned.add2(vpaned)
				label = gtk.Label(doc.pname)
				self.notebook.append_page(hpaned, label)
				self.notebook.show_tabs = True
				self.notebook.show_all()
			else:
				print err
		return

	def file_open (self,title='Open',parent=None, dirname=None, fname=None):
		if title == 'Save':
			dlg = gtk.FileChooserDialog('Save...', action=gtk.FILE_CHOOSER_ACTION_SAVE, buttons=(gtk.STOCK_OK,gtk.RESPONSE_OK,gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL))
		else:
			dlg = gtk.FileChooserDialog('Open...', parent, buttons=(gtk.STOCK_OK,gtk.RESPONSE_OK,gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL))
		dlg.set_local_only(True)
		resp = dlg.run()
		fname = dlg.get_filename()
		dlg.hide()
		if resp == gtk.RESPONSE_CANCEL:
			return None
		return fname

	def build_context_menu(self,txt,menu):
		pn = self.notebook.get_current_page()
		hd = self.das[pn].hd
		merge = gtk.UIManager()
		merge.insert_action_group(self.__create_action_group_popup(), 0)
		bounds = hd.txtdump_hex.get_buffer().get_selection_bounds()
		try:
			mergeid = merge.add_ui_from_string(ui_popup)
			menu = merge.get_widget("/EntryPopup")
			if not bounds:
				menu.set_sensitive(False)
			menu.popup(None,None,None,0,0)
		except gobject.GError, msg:
			print "building menus failed: %s" % msg

	def __create_action_group_popup(self):
		# GtkActionEntry
		entries = (
		  ( "child", None,					# name, stock id
			"Add child","<control>A",					  # label, accelerator
			"Add EMF command",							 # tooltip
			self.activate_child),
		);
		# Create the menubar and toolbar
		action_group = gtk.ActionGroup("PopupActions")
		action_group.add_actions(entries)
		return action_group

	def activate_child(self, menuitem):
		pn = self.notebook.get_current_page()


def main():
	ApplicationMainWindow()
	gtk.main()

if __name__ == '__main__':
	main()
