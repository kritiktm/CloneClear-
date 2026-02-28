import os
import hashlib
import threading
import time
import shutil
import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
from collections import defaultdict
import send2trash

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class DuplicateFinderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Поиск дубликатов файлов")
        self.geometry("1050x750")
        
        self.selected_folder = ""
        self.excluded_folders = set()
        self.target_move_folder = ""
        
        self.duplicates = {} # hash -> list of dicts with file info
        self.is_scanning = False
        self.total_freed_bytes = 0
        
        self.setup_ui()
        self.apply_treeview_style()

    def apply_treeview_style(self):
        style = ttk.Style(self)
        style.theme_use("default")
        
        bg_color = "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#ebebeb"
        fg_color = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#000000"
        sel_bg = "#1f538d"
        head_bg = "#343638" if ctk.get_appearance_mode() == "Dark" else "#d9d9d9"
        
        style.configure("Treeview", 
                        background=bg_color,
                        foreground=fg_color,
                        rowheight=25,
                        fieldbackground=bg_color,
                        bordercolor=bg_color,
                        borderwidth=0)
        style.map('Treeview', background=[('selected', sel_bg)])
        
        style.configure("Treeview.Heading",
                        background=head_bg,
                        foreground=fg_color,
                        relief="flat",
                        font=("Arial", 10, "bold"))
        style.map("Treeview.Heading",
                  background=[('active', sel_bg)])

    def setup_ui(self):
        # Top Frame (Controls)
        self.top_frame = ctk.CTkFrame(self)
        self.top_frame.pack(pady=10, padx=10, fill="x")
        
        # Row 1: Select Main Folder
        self.top_row1 = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.top_row1.pack(fill="x", pady=5)
        
        self.folder_btn = ctk.CTkButton(self.top_row1, text="Выбрать папку для сканирования", command=self.select_folder)
        self.folder_btn.pack(side="left", padx=10)
        
        self.folder_label = ctk.CTkLabel(self.top_row1, text="Папка не выбрана", anchor="w")
        self.folder_label.pack(side="left", padx=10, fill="x", expand=True)
        
        # Row 2: Excluded folders and Filter
        self.top_row2 = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.top_row2.pack(fill="x", pady=5)
        
        self.exclude_btn = ctk.CTkButton(self.top_row2, text="Исключить папку", command=self.add_excluded_folder, width=140)
        self.exclude_btn.pack(side="left", padx=10)
        
        self.excluded_label = ctk.CTkLabel(self.top_row2, text="Исключено папок: 0", anchor="w")
        self.excluded_label.pack(side="left", padx=10)
        
        self.clear_excluded_btn = ctk.CTkButton(self.top_row2, text="Сбросить исключения", command=self.clear_excluded, fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
        self.clear_excluded_btn.pack(side="left", padx=5)
        
        self.filter_var = ctk.StringVar(value="Все файлы")
        self.filter_combo = ctk.CTkComboBox(self.top_row2, values=["Все файлы", "Изображения", "Аудио", "Видео", "Документы"], variable=self.filter_var, state="readonly", width=150)
        self.filter_combo.pack(side="right", padx=10)
        
        self.scan_btn = ctk.CTkButton(self.top_row2, text="Найти дубликаты", command=self.start_scan, fg_color="green", hover_color="darkgreen")
        self.scan_btn.pack(side="right", padx=10)
        
        # Progress Frame
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=10)
        
        self.status_label = ctk.CTkLabel(self.progress_frame, text="Ожидание...")
        self.status_label.pack(side="left", padx=10)
        
        self.progressbar = ctk.CTkProgressBar(self.progress_frame)
        self.progressbar.pack(side="left", fill="x", expand=True, padx=10)
        self.progressbar.set(0)
        
        # Results Frame (Treeview)
        self.results_frame = ctk.CTkFrame(self)
        self.results_frame.pack(pady=5, padx=10, fill="both", expand=True)
        
        # Treeview Scrollbars
        self.tree_scroll_y = ttk.Scrollbar(self.results_frame)
        self.tree_scroll_y.pack(side="right", fill="y")
        
        self.tree = ttk.Treeview(self.results_frame, columns=("select", "path", "size"), show="tree headings", yscrollcommand=self.tree_scroll_y.set)
        self.tree_scroll_y.config(command=self.tree.yview)
        
        self.tree.heading("#0", text="Группа")
        self.tree.heading("select", text="Действие")
        self.tree.heading("path", text="Путь к файлу")
        self.tree.heading("size", text="Размер (MB)")
        
        self.tree.column("#0", width=100, stretch=False)
        self.tree.column("select", width=80, stretch=False, anchor="center")
        self.tree.column("path", width=500, stretch=True)
        self.tree.column("size", width=100, stretch=False, anchor="e")
        
        self.tree.pack(fill="both", expand=True)
        
        self.tree.tag_configure("group", font=("Arial", 10, "bold"), background="#444444" if ctk.get_appearance_mode() == "Dark" else "#cccccc")
        self.tree.tag_configure("file", font=("Arial", 10))
        
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)
        
        # Bottom Frame
        self.bottom_frame = ctk.CTkFrame(self)
        self.bottom_frame.pack(pady=10, padx=10, fill="x")
        
        self.select_all_btn = ctk.CTkButton(self.bottom_frame, text="Выбрать копии (оставить 1 оригинал)", command=self.select_smart)
        self.select_all_btn.pack(side="left", padx=10, pady=10)
        
        self.info_label = ctk.CTkLabel(self.bottom_frame, text="Выбрано: 0.00 MB", font=("Arial", 14, "bold"))
        self.info_label.pack(side="left", padx=15, pady=10)
        
        # Action selector
        self.action_var = ctk.StringVar(value="В корзину")
        self.action_combo = ctk.CTkComboBox(self.bottom_frame, values=["В корзину", "Переместить..."], variable=self.action_var, state="readonly", width=130, command=self.on_action_change)
        self.action_combo.pack(side="left", padx=10, pady=10)
        
        self.target_btn = ctk.CTkButton(self.bottom_frame, text="Указать куда переместить", command=self.select_target_folder, state="disabled", fg_color="transparent", border_width=1, text_color=("gray10", "gray90"))
        self.target_btn.pack(side="left", padx=5, pady=10)
        
        self.action_btn = ctk.CTkButton(self.bottom_frame, text="Выполнить действие", command=self.process_selected, fg_color="red", hover_color="darkred")
        self.action_btn.pack(side="right", padx=10, pady=10)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.selected_folder = os.path.normpath(folder)
            self.folder_label.configure(text=self.selected_folder, text_color=("black", "white"))
            
    def add_excluded_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку для исключения")
        if folder:
            norm_folder = os.path.normpath(folder)
            self.excluded_folders.add(norm_folder)
            self.update_excluded_label()
            
    def clear_excluded(self):
        self.excluded_folders.clear()
        self.update_excluded_label()
        
    def update_excluded_label(self):
        self.excluded_label.configure(text=f"Исключено папок: {len(self.excluded_folders)}")
        
    def select_target_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку для перемещения дубликатов")
        if folder:
            self.target_move_folder = os.path.normpath(folder)
            self.target_btn.configure(text=f"-> {os.path.basename(self.target_move_folder)}", fg_color="transparent")
            
    def on_action_change(self, choice):
        if choice == "Переместить...":
            self.target_btn.configure(state="normal")
            self.action_btn.configure(fg_color="#1f538d", hover_color="#14375e") # Blue for move
        else:
            self.target_btn.configure(state="disabled")
            self.action_btn.configure(fg_color="red", hover_color="darkred")

    def get_extensions_by_filter(self):
        filter_type = self.filter_var.get()
        if filter_type == "Изображения":
            return {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff'}
        elif filter_type == "Аудио":
            return {'.mp3', '.wav', '.flac', '.ogg', '.m4a'}
        elif filter_type == "Видео":
            return {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv'}
        elif filter_type == "Документы":
            return {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt'}
        return set()

    def update_progress(self, value, text):
        self.progressbar.set(value)
        self.status_label.configure(text=text)

    def start_scan(self):
        if not self.selected_folder:
            messagebox.showwarning("Внимание", "Сначала выберите папку для сканирования!")
            return
            
        if self.is_scanning:
            return
            
        self.is_scanning = True
        self.scan_btn.configure(state="disabled")
        self.folder_btn.configure(state="disabled")
        self.exclude_btn.configure(state="disabled")
        self.clear_excluded_btn.configure(state="disabled")
        self.select_all_btn.configure(state="disabled")
        self.action_btn.configure(state="disabled")
        
        # Clear treeview
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self.total_freed_bytes = 0
        self.update_freed_space_label()
        
        threading.Thread(target=self.scan_process, daemon=True).start()

    def get_chunk_hash(self, filepath, chunk_size=65536, full=False):
        hasher = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                if not full:
                    chunk = f.read(chunk_size)
                    hasher.update(chunk)
                else:
                    while chunk := f.read(chunk_size):
                        hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return None

    def scan_process(self):
        last_update = time.time()
        ext_filter = self.get_extensions_by_filter()
        is_all_files = self.filter_var.get() == "Все файлы"
        
        files_to_check = []
        for root, dirs, files in os.walk(self.selected_folder):
            # Пропускаем исключенные директории
            dirs[:] = [d for d in dirs if os.path.normpath(os.path.join(root, d)) not in self.excluded_folders]
            
            for file in files:
                if not is_all_files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext not in ext_filter:
                        continue
                filepath = os.path.join(root, file)
                files_to_check.append(filepath)
                
        total_files = len(files_to_check)
        if total_files == 0:
            self.after(0, self.finish_scan, {}, "Файлы для проверки не найдены.")
            return

        # 1. Группировка по размеру (быстро)
        size_dict = defaultdict(list)
        for i, filepath in enumerate(files_to_check):
            try:
                size = os.path.getsize(filepath)
                if size > 0: # Игнорируем пустые файлы
                    size_dict[size].append(filepath)
            except Exception:
                pass
            
            if time.time() - last_update > 0.1:
                progress = (i / total_files) * 0.1 # 10% сканирования
                self.after(0, self.update_progress, progress, f"Анализ размеров... {i}/{total_files} файлов")
                last_update = time.time()

        potential_dupes = {s: files for s, files in size_dict.items() if len(files) > 1}
        
        fast_files = []
        for files in potential_dupes.values():
            fast_files.extend(files)
            
        total_fast = len(fast_files)
        if total_fast == 0:
            self.after(0, self.finish_scan, {}, "Дубликатов не найдено.")
            return

        # 2. Быстрое хеширование (64KB)
        fast_hash_dict = defaultdict(list)
        for i, filepath in enumerate(fast_files):
            f_hash = self.get_chunk_hash(filepath, full=False)
            if f_hash:
                fast_hash_dict[f_hash].append(filepath)
                
            if time.time() - last_update > 0.1:
                progress = 0.1 + (i / total_fast) * 0.3 # 30% сканирования
                self.after(0, self.update_progress, progress, f"Быстрое хеширование (64KB)... {i}/{total_fast}")
                last_update = time.time()

        fast_dupes = {h: files for h, files in fast_hash_dict.items() if len(files) > 1}
        
        full_files = []
        for files in fast_dupes.values():
            full_files.extend(files)
            
        total_full = len(full_files)
        
        # 3. Полное хеширование для оставшихся
        full_hash_dict = defaultdict(list)
        for i, filepath in enumerate(full_files):
            file_hash = self.get_chunk_hash(filepath, full=True)
            if file_hash:
                full_hash_dict[file_hash].append(filepath)
                
            if time.time() - last_update > 0.1:
                progress = 0.4 + (i / total_full) * 0.6 # 60% сканирования
                self.after(0, self.update_progress, progress, f"Полное хеширование... {i}/{total_full}")
                last_update = time.time()

        final_dupes = {h: files for h, files in full_hash_dict.items() if len(files) > 1}
        
        self.after(0, self.finish_scan, final_dupes, f"Готово! Найдено групп дубликатов: {len(final_dupes)}")

    def finish_scan(self, duplicates, status_text):
        self.is_scanning = False
        self.scan_btn.configure(state="normal")
        self.folder_btn.configure(state="normal")
        self.exclude_btn.configure(state="normal")
        self.clear_excluded_btn.configure(state="normal")
        self.select_all_btn.configure(state="normal")
        self.action_btn.configure(state="normal")
        self.update_progress(1.0, status_text)
        self.duplicates = duplicates
        
        if not duplicates:
            if "не найдены" not in status_text.lower():
                messagebox.showinfo("Результат", "Дубликаты не найдены!")
            return
            
        # Заполняем Treeview
        for i, (h, files) in enumerate(duplicates.items()):
            size = os.path.getsize(files[0])
            size_mb = size / (1024 * 1024)
            group_id = self.tree.insert("", "end", text=f"Группа {i+1}", values=("", f"{len(files)} файла(ов)", f"{size_mb:.2f}"), tags=("group",), open=True)
            
            for filepath in files:
                display_path = os.path.relpath(filepath, self.selected_folder) if filepath.startswith(self.selected_folder) else filepath
                self.tree.insert(group_id, "end", text="", values=("[ ]", display_path, f"{size_mb:.2f}"), tags=("file", filepath, str(size)))

    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1": # 'select' column
                item = self.tree.identify_row(event.y)
                tags = self.tree.item(item, "tags")
                
                if "file" in tags:
                    vals = list(self.tree.item(item, "values"))
                    size_bytes = int(tags[2]) if len(tags) > 2 else 0
                    
                    if vals[0] == "[ ]":
                        vals[0] = "[X]"
                        self.total_freed_bytes += size_bytes
                    elif vals[0] == "[X]":
                        vals[0] = "[ ]"
                        self.total_freed_bytes -= size_bytes
                        
                    self.tree.item(item, values=vals)
                    self.update_freed_space_label()

    def update_freed_space_label(self):
        size_mb = self.total_freed_bytes / (1024 * 1024)
        self.info_label.configure(text=f"Выбрано: {size_mb:.2f} MB")

    def select_smart(self):
        if not self.duplicates: return
        
        self.total_freed_bytes = 0
        
        for group in self.tree.get_children():
            children = self.tree.get_children(group)
            if not children: continue
            
            first_child = children[0]
            first_vals = list(self.tree.item(first_child, "values"))
            first_vals[0] = "[ ]"
            self.tree.item(first_child, values=first_vals)
            
            for child in children[1:]:
                vals = list(self.tree.item(child, "values"))
                tags = self.tree.item(child, "tags")
                
                if "file" in tags:
                    if vals[0] == "[ ]":
                        vals[0] = "[X]"
                        size_bytes = int(tags[2]) if len(tags) > 2 else 0
                        self.total_freed_bytes += size_bytes
                    self.tree.item(child, values=vals)
                    
        self.update_freed_space_label()

    def process_selected(self):
        to_process = []
        for group in self.tree.get_children():
            for child in self.tree.get_children(group):
                vals = self.tree.item(child, "values")
                tags = self.tree.item(child, "tags")
                
                if vals[0] == "[X]" and "file" in tags:
                    filepath = tags[1]
                    to_process.append((child, filepath))
                    
        if not to_process:
            messagebox.showinfo("Инфо", "Нет выбранных файлов для действия.")
            return
            
        action = self.action_var.get()
        
        if action == "Переместить...":
            if not self.target_move_folder:
                messagebox.showwarning("Внимание", "Пожалуйста, сначала выберите папку для перемещения дубликатов!\n(Кнопка 'Указать куда переместить')")
                return
            prompt_msg = f"Вы уверены, что хотите переместить {len(to_process)} файлов в папку:\n{self.target_move_folder}?"
            success_status = "[-ПЕРЕМЕЩЕНО]"
            success_color = "orange"
        else:
            prompt_msg = f"Вы уверены, что хотите переместить в корзину {len(to_process)} файлов?"
            success_status = "[-УДАЛЕНО]"
            success_color = "red"
            
        if messagebox.askyesno("Подтверждение", prompt_msg):
            processed_count = 0
            for item_id, path in to_process:
                try:
                    clean_path = os.path.normpath(path)
                    
                    if action == "В корзину":
                        send2trash.send2trash(clean_path)
                    else: # Move
                        filename = os.path.basename(clean_path)
                        dest_path = os.path.join(self.target_move_folder, filename)
                        
                        # Handle identical filename collision in target folder
                        base, ext = os.path.splitext(filename)
                        counter = 1
                        while os.path.exists(dest_path):
                            dest_path = os.path.join(self.target_move_folder, f"{base}_{counter}{ext}")
                            counter += 1
                            
                        shutil.move(clean_path, dest_path)
                    
                    # Изменяем внешний вид обработанного файла
                    vals = list(self.tree.item(item_id, "values"))
                    vals[0] = success_status
                    vals[1] = vals[1] + (" (РАЗМЕЩЕНО В КОРЗИНЕ)" if action == "В корзину" else " (ПЕРЕМЕЩЕНО)")
                    self.tree.item(item_id, values=vals, tags=("processed",))
                    self.tree.tag_configure("processed", foreground=success_color)
                    
                    processed_count += 1
                except Exception as e:
                    print(f"Failed to process {path}: {e}")
                    
            self.total_freed_bytes = 0
            self.update_freed_space_label()
            
            messagebox.showinfo("Успех", f"Успешно обработано {processed_count} файлов.")

if __name__ == "__main__":
    app = DuplicateFinderApp()
    app.mainloop()
