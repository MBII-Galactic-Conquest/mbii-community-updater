import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import requests
import json
import os
import itertools
import shutil
import zipfile
import io
import sys

# ====================================================================
# REQUIRED MODULES:
# These are the modules that need to be installed via pip.
# You can install them by running this command in your terminal:
# pip install requests Pillow pygame
# ====================================================================

try:
    from PIL import Image, ImageTk
except ImportError:
    messagebox.showerror("Error", "The Pillow library is not installed. Please install it with 'pip install Pillow' and restart the application.")
    sys.exit()

try:
    import pygame.mixer as mixer
except ImportError:
    messagebox.showerror("Error", "The Pygame library is not installed. Please install it with 'pip install pygame' and restart the application.")
    sys.exit()

class GitHubReleaseManager:
    """
    A Tkinter application to download a specific release from a GitHub repository.
    This version includes a custom, fully consistent dark theme, handles API rate limiting,
    and now includes functionality to fetch a repositories.json file from a hardcoded repository on startup.
    It also now saves all user-generated files inside a 'cache' folder for better PyInstaller compatibility.
    """

    HARDCODED_REPOSITORIES_REPO_URL = "https://raw.githubusercontent.com/MBII-Galactic-Conquest/mbii-community-updater/main/repositories.json"

    def __init__(self, master):
        """
        Initializes the application window and widgets.
        
        Args:
            master (tk.Tk): The main window object.
        """
        self.master = master
        self.master.title("MBII Community Updater")
        
        # Set a compact, non-resizable window size
        self.master.geometry("502x351")
        self.master.resizable(False, False)
        
        # --- Application State Variables ---
        self.repositories = []
        self.client_data = {}
        self.current_repo_data = {}
        self.available_releases = {}
        self.download_path = None
        self.selected_repo_url = None
        self.selected_release_tag = None
        self.current_owner = ""
        self.current_repo = ""
        self.is_rate_limited = False # Flag to prevent multiple rate limit popups and actions
        self.fetched_requirements = {}
        
        # This instance variable is crucial for preventing the background image
        # from being garbage collected by Python.
        self.bg_image_ref = None

        # --- File Paths are now relative to a 'cache' directory, except for music.mp3 ---
        self.create_cache_directory()
        self.repositories_file = os.path.join("cache", "repositories.json")
        self.client_file = os.path.join("cache", "client.json")
        self.mbii_directory_file = os.path.join("cache", "mbiidirectory.json")
        # Music file is now expected in the root directory, not the cache
        self.music_file = "music.mp3"
        self.requirements_file = os.path.join("cache", "requirements.json")
        
        # UI for loading screen
        self.loading_window = None
        self.loading_animation = None
        self.spinner = itertools.cycle(['|', '/', '-', '\\'])
        
        # String variable for the download path display
        self.download_path_var = tk.StringVar(self.master, value="Not Set")
        # String variable for the repository description
        self.description_var = tk.StringVar(self.master, value="Select a repository to see its description.")
        
        # Music player state
        self.is_music_playing = False

        # Initialize the pygame mixer
        mixer.init()
        
        self.create_widgets()
        
        # --- NEW: Fetch requirements from the hardcoded URL with local fallback on startup ---
        self.status_label.config(text="Fetching requirements...", fg="#3498db")
        threading.Thread(target=self.fetch_hardcoded_requirements, daemon=True).start()

        self.load_repositories()
        self.load_mbii_directory()
        self.load_client_data()
        self.load_sound_settings()
        self.populate_repositories()
        self.update_download_button_state()
        self.update_remove_button_state()
        
        # Bind the close event to a handler
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_cache_directory(self):
        """Creates a 'cache' directory in the application's root if it doesn't exist."""
        if not os.path.exists("cache"):
            os.makedirs("cache")

    def create_widgets(self):
        """
        Creates and lays out all the widgets for the application, using a custom, consistent dark theme.
        This version ensures the background image is visible by using a semi-transparent overlay.
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # --- Icon Loading Logic ---
        icon_path_ico = os.path.join(script_dir, 'icon.ico')
        if os.path.exists(icon_path_ico):
            try:
                self.master.iconbitmap(icon_path_ico)
            except tk.TclError:
                print("WARNING: 'icon.ico' found but failed to load. Skipping window icon.")
        else:
            try:
                icon_path_png = os.path.join(script_dir, 'icon.png')
                icon_image = Image.open(icon_path_png)
                icon_photo = ImageTk.PhotoImage(icon_image)
                self.master.iconphoto(True, icon_photo)
            except (tk.TclError, FileNotFoundError, IOError):
                print("WARNING: Neither 'icon.ico' nor 'icon.png' found. Skipping window icon.")

        # --- Define Colors for a Unified Theme ---
        dark_background_color = "#121212"  # A very dark background for consistency
        dark_widget_color = "#1e1e1e"     # A slightly lighter dark color for widgets
        text_color = "white"
        highlight_color = "#4a4a4a"       # A subtle highlight color for selections
        border_color = "#333333"          # A darker gray for borders

        # Create a Canvas that fills the entire master window
        canvas = tk.Canvas(self.master, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        window_width = 502
        window_height = 351
        
        try:
            image_path = os.path.join(script_dir, 'background.png')
            pil_image = Image.open(image_path)
            resized_image = pil_image.resize((window_width, window_height), Image.LANCZOS)
            self.bg_image_ref = ImageTk.PhotoImage(resized_image)
            canvas.create_image(0, 0, image=self.bg_image_ref, anchor="nw")
            
            # Create a semi-transparent dark overlay on the canvas
            # This is the key to letting the background image show through while maintaining a dark theme.
            canvas.create_rectangle(0, 0, window_width, window_height, fill=dark_background_color, stipple='gray50')
            
        except (tk.TclError, FileNotFoundError, IOError):
            print("WARNING: 'background.png' not found or is invalid. Falling back to a solid dark background.")

        # Use a new frame to hold all the content, and place it *on* the canvas
        content_frame = tk.Frame(canvas, bg="#121212")
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)
        canvas.create_window(window_width / 2, window_height / 2, window=content_frame, anchor="center")

        # --- Configure a custom ttk style for widgets ---
        style = ttk.Style()
        style.theme_create("CustomDark", parent="alt", settings={
            "TCombobox": {
                "configure": {
                    "selectbackground": highlight_color,
                    "fieldbackground": dark_widget_color,
                    "background": dark_widget_color,
                    "foreground": text_color,
                    "bordercolor": border_color,
                    "arrowcolor": text_color,
                    "padding": 3,
                },
                "map": {
                    "fieldbackground": [("readonly", dark_widget_color)],
                    "selectbackground": [("readonly", dark_widget_color)],
                    "selectforeground": [("readonly", text_color)],
                }
            },
            "TCombobox.listbox": {
                "configure": {
                    "background": dark_widget_color,
                    "foreground": text_color,
                    "selectbackground": highlight_color,
                    "selectforeground": text_color,
                    "bordercolor": border_color,
                    "relief": "flat",
                }
            },
            "TLabel": {
                "configure": {
                    "background": dark_background_color,
                    "foreground": text_color,
                }
            },
            "TFrame": {
                "configure": {
                    "background": dark_background_color,
                }
            },
            # A new style for the download path entry with a light background and dark text
            "DownloadPath.TEntry": {
                "configure": {
                    "fieldbackground": "#f0f0f0",  # Light gray background
                    "foreground": "black",         # Black text
                    "bordercolor": border_color,
                },
                "map": {
                    "fieldbackground": [("readonly", "#f0f0f0")],
                }
            },
            "TButton": {
                "configure": {
                    "background": border_color,
                    "foreground": text_color,
                    "bordercolor": border_color,
                    "relief": "flat",
                },
                "map": {
                    "background": [("active", highlight_color)],
                }
            },
            "TScrollbar": {
                "configure": {
                    "background": border_color,
                    "troughcolor": dark_widget_color,
                    "bordercolor": border_color,
                }
            },
        })
        style.theme_use("CustomDark")

        # Header Label
        #header_label = tk.Label(content_frame, text="", font=("Helvetica", 14, "bold"), bg=dark_background_color, fg=text_color)
        #header_label.grid(row=0, column=0, columnspan=2, pady=(0, 5), sticky="ew")

        # Saved Repositories Listbox Section
        list_frame = tk.LabelFrame(content_frame, text="Community Content", padx=5, pady=5, bg="#121212", fg=text_color, borderwidth=1, relief="flat")
        list_frame.grid(row=1, column=0, columnspan=2, pady=5, sticky="ew")
        list_frame.grid_columnconfigure(0, weight=1)
        
        scrollbar = tk.Scrollbar(list_frame, background=border_color, troughcolor=dark_widget_color, activebackground=highlight_color)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox_repos = tk.Listbox(list_frame, height=6, yscrollcommand=scrollbar.set, font=("Helvetica", 9), bg=dark_widget_color, fg=text_color, selectbackground=highlight_color, highlightthickness=0, relief="flat")
        self.listbox_repos.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox_repos.bind("<<ListboxSelect>>", self.on_listbox_select)
        scrollbar.config(command=self.listbox_repos.yview)
        
        # Repository Description Label
        self.description_label = tk.Label(content_frame, textvariable=self.description_var, wraplength=480, justify=tk.CENTER, bg=dark_background_color, fg=text_color, font=("Helvetica", 9, "italic"))
        self.description_label.grid(row=2, column=0, columnspan=2, pady=(3,0), sticky="ew")

        # Separator
        tk.Frame(content_frame, height=2, bg=border_color).grid(row=3, column=0, columnspan=2, pady=5, sticky="ew")

        # Release Version Dropdown
        self.label_release = tk.Label(content_frame, text="Select a Release Version:", bg=dark_background_color, fg=text_color, font=("Helvetica", 9, "bold"))
        self.label_release.grid(row=4, column=0, padx=5, pady=(3,0), sticky="e")

        self.release_version_combo = ttk.Combobox(content_frame, style="TCombobox", state="disabled", width=37)
        self.release_version_combo.grid(row=4, column=1, padx=5, pady=(3,0), sticky="w")
        self.release_version_combo['values'] = ['Please select a repository...']
        self.release_version_combo.set('Please select a repository...')
        self.release_version_combo.bind("<<ComboboxSelected>>", self.on_release_version_select)

        # Download Path Section
        self.download_path_label = tk.Label(content_frame, text="Download Path:", bg=dark_background_color, fg=text_color, font=("Helvetica", 9, "bold"))
        self.download_path_label.grid(row=5, column=0, padx=5, pady=3, sticky="e")
        
        path_button_frame = tk.Frame(content_frame, bg=dark_background_color)
        path_button_frame.grid(row=5, column=1, padx=5, pady=3, sticky="w")
        
        # Use the new style for the Entry widget
        self.download_path_display = ttk.Entry(path_button_frame, textvariable=self.download_path_var, width=30, state="readonly", style="DownloadPath.TEntry")
        self.download_path_display.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.download_path_button = tk.Button(path_button_frame, text="Browse", command=self.select_download_path, bg=border_color, fg=text_color, activebackground=highlight_color, relief="raised")
        self.download_path_button.pack(side=tk.LEFT)
        
        # Status Label and Buttons
        self.status_label = tk.Label(content_frame, text="", bg=dark_background_color, fg="#3498db")
        self.status_label.grid(row=6, column=0, columnspan=2, pady=(3, 2), sticky="ew")
        
        self.button_frame = tk.Frame(content_frame, bg=dark_background_color)
        self.button_frame.grid(row=7, column=0, columnspan=2, pady=(2, 0))

        self.download_button = tk.Button(self.button_frame, text="Download", state="disabled", command=self.on_download, bg="#4CAF50", fg=text_color, activebackground="#45a049", relief="raised", font=("Helvetica", 9, "bold"))
        self.download_button.pack(side=tk.LEFT, padx=5)
        self.download_button.bind("<Enter>", lambda e: e.widget.configure(bg="#45a049"))
        self.download_button.bind("<Leave>", lambda e: e.widget.configure(bg="#4CAF50"))

        self.remove_button = tk.Button(self.button_frame, text="Remove", state="disabled", command=self.on_remove, bg="#e74c3c", fg=text_color, activebackground="#c0392b", relief="raised", font=("Helvetica", 9, "bold"))
        self.remove_button.pack(side=tk.LEFT, padx=5)
        self.remove_button.bind("<Enter>", lambda e: e.widget.configure(bg="#c0392b"))
        self.remove_button.bind("<Leave>", lambda e: e.widget.configure(bg="#e74c3c"))
        
        self.music_button = tk.Button(self.button_frame, text="Music Off", command=self.toggle_music, bg="#3498db", fg=text_color, activebackground="#2980b9", relief="raised", font=("Helvetica", 9, "bold"))
        self.music_button.pack(side=tk.LEFT, padx=5)
        self.music_button.bind("<Enter>", lambda e: e.widget.configure(bg="#2980b9"))
        self.music_button.bind("<Leave>", lambda e: e.widget.configure(bg="#3498db"))

    def on_close(self):
        """Handler for the window close event."""
        self.master.destroy()

    def handle_rate_limit(self):
        """
        Handles a 403 rate limit error by showing a popup and exiting the application gracefully.
        This prevents the looping and TclError. The flag `is_rate_limited` ensures this only happens once.
        """
        if not self.is_rate_limited:
            self.is_rate_limited = True
            messagebox.showwarning(
                "Rate Limit Exceeded",
                "Refreshed due to being rate limited, please wait approximately one minute."
            )
            # Gracefully close the application.
            self.master.quit()

    def load_repositories(self):
        """Loads repositories from a local `repositories.json` file."""
        if os.path.exists(self.repositories_file):
            try:
                with open(self.repositories_file, 'r') as f:
                    self.repositories = json.load(f)
                self.status_label.config(text="Successfully loaded repository list from file.", fg="#4CAF50")
            except (IOError, json.JSONDecodeError) as e:
                messagebox.showerror("Error", f"Could not load local repositories file: {e}")
                self.repositories = []
        else:
            self.status_label.config(text="`repositories.json` file not found. Please create it inside the 'cache' folder.", fg="#e74c3c")
            self.repositories = []

    def load_client_data(self):
        """Loads the local client data (download history and music settings) from `client.json`."""
        if os.path.exists(self.client_file):
            try:
                with open(self.client_file, 'r') as f:
                    self.client_data = json.load(f)
            except (IOError, json.JSONDecodeError):
                self.client_data = {}
        else:
            self.client_data = {}

    def save_client_data(self):
        """Saves the current client data (download history and music settings) to `client.json`."""
        try:
            with open(self.client_file, 'w') as f:
                json.dump(self.client_data, f, indent=4)
        except IOError as e:
            messagebox.showerror("Error", f"Could not save client data to file: {e}")

    def save_music_settings(self):
        """Saves the current music settings to client_data and then to the file."""
        music_settings = self.client_data.get("music_settings", {})
        music_settings["auto_play"] = self.is_music_playing
        music_settings["volume"] = mixer.music.get_volume() if mixer.get_init() else 0.15625
        self.client_data["music_settings"] = music_settings
        self.save_client_data()
            
    def load_sound_settings(self):
        """Loads sound settings from `client.json` or uses defaults."""
        music_settings = self.client_data.get("music_settings", {})
        auto_play = music_settings.get("auto_play", True)
        volume = music_settings.get("volume", 0.5)
        
        if mixer.get_init():
            mixer.music.set_volume(max(0, min(1, volume)))
            if auto_play and os.path.exists(self.music_file):
                self.play_music()

    def play_music(self):
        """Plays the music.mp3 file if it exists."""
        if os.path.exists(self.music_file):
            try:
                mixer.music.load(self.music_file)
                mixer.music.play(-1)
                self.is_music_playing = True
                self.music_button.config(text="Music On")
                self.save_music_settings()
            except mixer.error as e:
                messagebox.showerror("Music Error", f"Failed to play music file: {e}")
                self.is_music_playing = False
                self.music_button.config(text="Music Off")
        else:
            self.is_music_playing = False
            self.music_button.config(text="Music Off")
            messagebox.showwarning("File Not Found", f"Music file '{self.music_file}' not found.")
            
    def toggle_music(self):
        """Toggles music playback on and off."""
        if self.is_music_playing:
            mixer.music.pause()
            self.is_music_playing = False
            self.music_button.config(text="Music Off")
        else:
            if mixer.music.get_busy():
                mixer.music.unpause()
            else:
                self.play_music()
            self.is_music_playing = True
            self.music_button.config(text="Music On")
        
        self.save_music_settings()

    def load_mbii_directory(self):
        """
        Loads the MBII directory from a local JSON file.
        """
        if os.path.exists(self.mbii_directory_file):
            try:
                with open(self.mbii_directory_file, 'r') as f:
                    data = json.load(f)
                    path = data.get("path")
                    if path and os.path.isdir(path):
                        self.download_path = path
                        self.download_path_var.set(path)
                        self.status_label.config(text=f"Loaded saved MBII directory.", fg="#3498db")
                    else:
                        self.status_label.config(text="Saved MBII directory not found. Please select a new one.", fg="orange")
                        self.download_path = None
                        self.download_path_var.set("Not Set")
            except (IOError, json.JSONDecodeError):
                self.download_path = None
                self.download_path_var.set("Not Set")
                pass
        else:
            self.download_path = None
            self.download_path_var.set("Not Set")
        
        self.update_download_button_state()

    def save_mbii_directory(self, path):
        """Saves the MBII directory path to a JSON file."""
        try:
            with open(self.mbii_directory_file, 'w') as f:
                json.dump({"path": path}, f, indent=4)
        except IOError as e:
            messagebox.showerror("Error", f"Could not save MBII directory to file: {e}")

    def populate_repositories(self):
        """
        Clears and repopulates the Listbox with the current repositories.
        The rate-limit check is now removed from this function to prevent startup spam.
        """
        self.listbox_repos.delete(0, tk.END)
        for i, repo in enumerate(self.repositories):
            repo_name_display = repo.get('custom_name') or repo['url'].rstrip('/').split('/')[-1]
            self.listbox_repos.insert(tk.END, repo_name_display)
            # Check for a previously downloaded tag to color the listbox item.
            # This check is local and does not hit the GitHub API.
            last_downloaded = self.client_data.get(repo['url'], {}).get('last_tag')
            if last_downloaded:
                self.listbox_repos.itemconfig(i, {'fg': 'green'})
            else:
                self.listbox_repos.itemconfig(i, {'fg': 'white'})
        
        self.reset_ui()


    def select_download_path(self):
        """Opens a file dialog for the user to select a download directory and validates it."""
        path = filedialog.askdirectory()
        if path:
            if 'MBII' in path.upper():
                self.download_path = path
                self.download_path_var.set(path)
                self.save_mbii_directory(path)
            else:
                messagebox.showerror("Invalid Directory", "The selected directory must contain 'MBII' in its name.")
                self.download_path = None
                self.download_path_var.set("Not Set")
        self.update_download_button_state()

    def on_listbox_select(self, event):
        """
        Handles a repository selection, fetching its releases in a new thread.
        This is where the API call and rate-limit check now occur.
        """
        if self.is_rate_limited:
            return

        selection = self.listbox_repos.curselection()
        
        if not selection and self.selected_repo_url is not None:
            return
        
        if not selection:
            self.reset_ui()
            return

        index = selection[0]
        self.current_repo_data = self.repositories[index]
        self.selected_repo_url = self.current_repo_data.get('url', '')
        description = self.current_repo_data.get('description', 'No description available.')
        self.description_var.set(description)
        
        self.release_version_combo.set("Loading releases...")
        self.release_version_combo.config(state="disabled")
        self.selected_release_tag = None

        if self.selected_repo_url:
            try:
                parts = self.selected_repo_url.rstrip('/').split('/')
                self.current_owner = parts[-2]
                self.current_repo = parts[-1]
            except IndexError:
                self.current_owner = ""
                self.current_repo = ""
                messagebox.showerror("Error", f"Invalid repository URL format for '{self.selected_repo_url}'.")
                self.reset_ui()
                self.selected_repo_url = None
                return
        
        self.status_label.config(text="Fetching releases...", fg="#3498db")
        self.update_download_button_state()
        self.update_remove_button_state()

        # Fetch releases in a new thread to prevent the UI from freezing
        threading.Thread(target=self.fetch_releases_for_repo, daemon=True).start()

    def fetch_hardcoded_requirements(self):
        """
        Fetches the requirements.json from the hardcoded repository.
        If that fails, it falls back to a local file in the cache directory.
        """
        try:
            url = self.HARDCODED_REPOSITORIES_REPO_URL
            response = requests.get(url)
            response.raise_for_status()
            
            self.fetched_requirements = response.json()
            self.master.after(0, lambda: self.status_label.config(text="Repository requirements loaded from remote URL.", fg="#4CAF50"))

        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            # Capture the error message to avoid the NameError in the lambda
            error_message = str(e)
            
            # Fallback to local file if the remote fetch fails
            if os.path.exists(self.requirements_file):
                try:
                    with open(self.requirements_file, 'r') as f:
                        self.fetched_requirements = json.load(f)
                    self.master.after(0, lambda: self.status_label.config(text="Could not fetch remote requirements. Loaded local fallback.", fg="orange"))
                except (IOError, json.JSONDecodeError):
                    self.fetched_requirements = {}
                    self.master.after(0, lambda: self.status_label.config(text="Failed to load local requirements file. Proceeding without requirements.", fg="#e74c3c"))
            else:
                self.fetched_requirements = {}
                self.master.after(0, lambda: self.status_label.config(text="No remote or local requirements file found. Proceeding.", fg="orange"))
                # Pass the error message to the lambda
                self.master.after(0, lambda msg=error_message: messagebox.showwarning("Requirements Warning", f"Could not fetch or find requirements.json.\nError: {msg}"))

    def fetch_releases_for_repo(self):
        """Fetches all releases for the selected repository and updates the dropdown."""
        if self.is_rate_limited:
            return
            
        try:
            api_url = f"https://api.github.com/repos/{self.current_owner}/{self.current_repo}/releases"
            response = requests.get(api_url)
            response.raise_for_status()
            
            releases = response.json()
            if not releases:
                self.master.after(0, lambda: self.release_version_combo.config(values=["No releases found"], state="disabled"))
                self.master.after(0, lambda: self.release_version_combo.set("No releases found"))
                self.master.after(0, lambda: self.status_label.config(text="No releases found for this repository.", fg="#e74c3c"))
                return

            self.available_releases = {r['tag_name']: r for r in releases}
            release_tags = [r['tag_name'] for r in releases]
            
            self.master.after(0, lambda: self.release_version_combo.config(values=release_tags, state="readonly"))
            
            if release_tags:
                self.master.after(0, lambda: self.release_version_combo.set(release_tags[0]))
                self.master.after(0, self.on_release_version_select)
            else:
                self.master.after(0, lambda: self.release_version_combo.set("No releases available"))
                self.master.after(0, lambda: self.release_version_combo.config(state="disabled"))

            self.master.after(0, lambda: self.status_label.config(text=f"Releases loaded. Please select a version.", fg="#3498db"))
            self.master.after(0, self.update_download_button_state)
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                self.master.after(0, self.handle_rate_limit)
            else:
                self.master.after(0, lambda: self.status_label.config(text=f"Error fetching releases: {e}", fg="#e74c3c"))
                self.master.after(0, lambda: messagebox.showerror("Network Error", f"Failed to get release list.\nError: {e}"))
                self.master.after(0, lambda: self.release_version_combo.set("Error fetching releases"))
                self.master.after(0, lambda: self.release_version_combo.config(values=["Error fetching releases"], state="disabled"))
                self.master.after(0, self.update_download_button_state)
        except requests.exceptions.RequestException as e:
            self.master.after(0, lambda: self.status_label.config(text=f"Error fetching releases: {e}", fg="#e74c3c"))
            self.master.after(0, lambda: messagebox.showerror("Network Error", f"Failed to get release list.\nError: {e}"))
            self.master.after(0, lambda: self.release_version_combo.set("Error fetching releases"))
            self.master.after(0, lambda: self.release_version_combo.config(values=["Error fetching releases"], state="disabled"))
            self.master.after(0, self.update_download_button_state)

    def on_release_version_select(self, event=None):
        """
        Handles the selection of a new release version from the dropdown.
        """
        selected_tag = self.release_version_combo.get()
        if selected_tag in self.available_releases:
            self.selected_release_tag = selected_tag
            self.status_label.config(text=f"Selected release version: {selected_tag}. Ready to download.", fg="#3498db")
        else:
            self.selected_release_tag = None
            self.status_label.config(text="No valid release version selected.", fg="#e74c3c")
        self.update_download_button_state()
        
    def update_download_button_state(self):
        """Updates the download button state based on all prerequisites being met."""
        is_repo_selected = self.selected_repo_url is not None
        is_version_selected = self.selected_release_tag is not None
        is_path_valid = self.download_path is not None and os.path.isdir(self.download_path) and 'MBII' in self.download_path.upper()
        
        if is_repo_selected and is_version_selected and is_path_valid:
            self.download_button.config(state="normal")
        else:
            self.download_button.config(state="disabled")

    def update_remove_button_state(self):
        """Updates the remove button state based on whether files are recorded for the current repo."""
        if self.selected_repo_url and self.selected_repo_url in self.client_data and self.client_data[self.selected_repo_url].get('file_list'):
            self.remove_button.config(state="normal")
        else:
            self.remove_button.config(state="disabled")

    def on_download(self):
        """Starts the download process in a separate thread."""
        if not self.download_path or 'MBII' not in self.download_path.upper():
            messagebox.showerror("Error", "Please select a valid MBII Directory first.")
            return

        if not self.selected_release_tag or self.selected_release_tag not in self.available_releases:
            messagebox.showerror("Error", "Please select a release version to download.")
            return

        self.download_button.config(state=tk.DISABLED)
        self.remove_button.config(state=tk.DISABLED)
        self.status_label.config(text=f"Starting download for '{self.current_repo}' version '{self.selected_release_tag}'...", fg="#3498db")
        
        self.create_loading_window()
        threading.Thread(target=self.download_release_by_tag, daemon=True).start()

    def download_release_by_tag(self):
        """Downloads and extracts the selected release from GitHub."""
        try:
            release_data = self.available_releases.get(self.selected_release_tag)
            if not release_data:
                self.master.after(0, lambda: self.status_label.config(text="Error: Could not find release data.", fg="#e74c3c"))
                return

            assets = release_data.get('assets', [])
            zip_asset = next((asset for asset in assets if asset['name'].endswith('.zip')), None)

            if not zip_asset:
                self.master.after(0, lambda: self.status_label.config(text="Error: No .zip release asset found for this version.", fg="#e74c3c"))
                return
            
            asset_name = zip_asset['name']
            download_url = zip_asset['browser_download_url']
            
            self.master.after(0, lambda: self.status_label.config(text=f"Downloading '{asset_name}'...", fg="#3498db"))
            
            file_response = requests.get(download_url, stream=True)
            file_response.raise_for_status()

            zip_in_memory = io.BytesIO(file_response.content)

            self.master.after(0, lambda: self.status_label.config(text=f"Extracting '{asset_name}'...", fg="#3498db"))
            
            file_list = []
            with zipfile.ZipFile(zip_in_memory, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                zip_ref.extractall(self.download_path)
            
            # Here you could potentially use the fetched_requirements to do a post-extraction check
            # For example:
            # required_files = self.fetched_requirements.get("files", [])
            # for required_file in required_files:
            #     if required_file not in file_list:
            #         messagebox.showwarning("Missing File", f"The required file '{required_file}' was not found in the release.")

            self.client_data[self.selected_repo_url] = {
                'last_tag': self.selected_release_tag,
                'file_list': file_list
            }
            self.save_client_data()

            self.master.after(0, lambda: self.status_label.config(text=f"Download and extraction complete!", fg="#4CAF50"))
            self.master.after(0, lambda: messagebox.showinfo("Success", f"Download and extraction complete! Files saved to:\n{self.download_path}"))
            self.master.after(0, self.populate_repositories)
            self.master.after(0, self.update_remove_button_state)

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                self.master.after(0, self.handle_rate_limit)
            else:
                self.master.after(0, lambda: self.status_label.config(text=f"Network Error: {e}", fg="#e74c3c"))
                self.master.after(0, lambda: messagebox.showerror("Network Error", f"Failed to download the release. Please check the URL and your internet connection.\nError: {e}"))
        except requests.exceptions.RequestException as e:
            self.master.after(0, lambda: self.status_label.config(text=f"Network Error: {e}", fg="#e74c3c"))
            self.master.after(0, lambda: messagebox.showerror("Network Error", f"Failed to download the release. Please check the URL and your internet connection.\nError: {e}"))
        except zipfile.BadZipFile:
            self.master.after(0, lambda: self.status_label.config(text="Error: The downloaded file is not a valid zip archive.", fg="#e74c3c"))
            self.master.after(0, lambda: messagebox.showerror("Extraction Error", "The downloaded file is not a valid zip archive."))
        except Exception as e:
            self.master.after(0, lambda: self.status_label.config(text=f"An unexpected error occurred: {e}", fg="#e74c3c"))
            self.master.after(0, lambda: messagebox.showerror("Error", f"An unexpected error occurred: {e}"))
        finally:
            if self.loading_window and self.loading_window.winfo_exists():
                self.master.after_cancel(self.loading_animation)
                self.loading_window.destroy()
            self.master.after(0, self.update_download_button_state)

    def on_remove(self):
        """Removes the downloaded files from the last installed release and updates the UI."""
        if not self.selected_repo_url:
            messagebox.showerror("Error", "Please select a repository first.")
            return

        if self.selected_repo_url not in self.client_data or 'file_list' not in self.client_data[self.selected_repo_url]:
            messagebox.showinfo("No Files Found", f"No downloaded files recorded for this repository.")
            return

        file_list_to_delete = self.client_data[self.selected_repo_url]['file_list']

        response = messagebox.askyesno(
            "Confirm Deletion",
            f"WARNING: This will attempt to delete all {len(file_list_to_delete)} files associated with this release. Proceed?"
        )
        
        if not response:
            return

        self.status_label.config(text="Removing files...", fg="#3498db")
        errors = []

        for filename in file_list_to_delete:
            full_path = os.path.join(self.download_path, filename)
            try:
                if os.path.isfile(full_path):
                    os.remove(full_path)
                elif os.path.isdir(full_path):
                    shutil.rmtree(full_path)
            except OSError as e:
                errors.append(f"Could not delete '{full_path}': {e}")
        
        del self.client_data[self.selected_repo_url]
        self.save_client_data()

        self.populate_repositories()
        self.update_remove_button_state()
        self.reset_ui()
        
        if errors:
            messagebox.showwarning("Deletion with Errors", f"Files removed, but some errors occurred:\n\n" + "\n".join(errors))
        else:
            messagebox.showinfo("Success", "All associated files have been removed.")
        self.status_label.config(text="File removal complete.", fg="#4CAF50")
        
    def reset_ui(self):
        """Resets the UI to its initial state."""
        self.listbox_repos.selection_clear(0, tk.END)
        self.selected_repo_url = None
        self.selected_release_tag = None
        self.release_version_combo['state'] = 'disabled'
        self.release_version_combo['values'] = ['Please select a repository...']
        self.release_version_combo.set('Please select a repository...')
        self.description_var.set("Select a repository to see its description.")
        self.update_download_button_state()
        self.update_remove_button_state()
        self.status_label.config(text="", fg="#3498db")

    def create_loading_window(self):
        """Creates and shows a loading popup window with a gray background."""
        self.loading_window = tk.Toplevel(self.master)
        self.loading_window.title("Downloading...")
        self.loading_window.geometry("300x100")
        self.loading_window.configure(bg="#f0f0f0")
        self.loading_window.resizable(False, False)
        self.loading_window.grab_set()
        
        x = self.master.winfo_x() + self.master.winfo_width() // 2 - 150
        y = self.master.winfo_y() + self.master.winfo_height() // 2 - 50
        self.loading_window.geometry(f'+{x}+{y}')

        tk.Label(self.loading_window, text="Downloading release...", font=("Helvetica", 12), bg="#f0f0f0").pack(pady=10)
        self.loading_label = tk.Label(self.loading_window, text=" | ", font=("Helvetica", 16, "bold"), bg="#f0f0f0")
        self.loading_label.pack(pady=5)
        
        self.update_spinner()
    
    def update_spinner(self):
        """Updates the spinner text on the loading label."""
        if self.loading_window and self.loading_window.winfo_exists():
            self.loading_label.config(text=f' {next(self.spinner)} ')
            self.loading_animation = self.master.after(100, self.update_spinner)
    
if __name__ == "__main__":
    root = tk.Tk()
    app = GitHubReleaseManager(root)
    root.mainloop()
