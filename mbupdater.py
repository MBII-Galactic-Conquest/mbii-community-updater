import tkinter as tk
from tkinter import ttk, filedialog
import concurrent.futures
import threading
import requests
import json
import os
import itertools
import shutil
import zipfile
import socket
import time
import io
import sys
import re

# ====================================================================
# REQUIRED MODULES:
# These are the modules that need to be installed via pip.
# You can install them by running this command in your terminal:
# pip install requests Pillow pygame
# ====================================================================

try:
    from PIL import Image, ImageTk
except ImportError:
    # Use a custom messagebox for this error as well
    root_error = tk.Tk()
    root_error.withdraw()
    tk.messagebox.showerror("Error", "The Pillow library is not installed. Please install it with 'pip install Pillow' and restart the application.")
    sys.exit()

try:
    import pygame.mixer as mixer
except ImportError:
    root_error = tk.Tk()
    root_error.withdraw()
    tk.messagebox.showerror("Error", "The Pygame library is not installed. Please install it with 'pip install pygame' and restart the application.")
    sys.exit()

try:
    from bs4 import BeautifulSoup
except ImportError:
    root_error = tk.Tk()
    root_error.withdraw()
    tk.messagebox.showerror("Error", "The BeautifulSoup library is not installed. Please install it with 'pip install beautifulsoup4 lxml' and restart the application.")
    sys.exit()

def get_resource_path(filename):
    """Returns the correct path for PyInstaller-bundled resources."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.abspath("."), filename)

def extract_zip_contents(zip_data, target_directory):
    """
    Extracts the contents of a ZIP file, stripping the common root directory 
    (e.g., 'MBII/') to prevent unwanted nested folders (e.g., /Target/MBII/MBII).
    
    Args:
        zip_data (bytes): The content of the zip file as bytes.
        target_directory (str): The final destination folder.
    """
    try:
        # 1. Open the zip archive from the byte stream
        with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
            
            name_list = zf.namelist()
            if not name_list:
                return # Zip is empty

            # 2. Identify the common root directory
            # Finds the longest common prefix (e.g., 'MBII/').
            root_dir = os.path.commonprefix(name_list)
            
            # Ensure the root_dir is a single-level directory name ending with a separator
            # If the path is complicated (e.g., 'mod/MBII/'), we treat it as no root.
            if not root_dir.endswith('/') or root_dir.count('/') > 1:
                 # If no clear single root directory, set root_dir to empty
                root_dir = ''

            # 3. Extract all files, modifying the path
            for member in name_list:
                
                # Calculate the new path by stripping the root directory
                if root_dir and member.startswith(root_dir):
                    # Strip the root directory (e.g., 'MBII/file' becomes 'file')
                    arcname = member[len(root_dir):]
                else:
                    arcname = member
                
                # Skip empty paths (the root folder itself) or directories
                if not arcname or arcname.endswith('/'):
                    continue

                # The full extraction path
                dest_path = os.path.join(target_directory, arcname)
                
                # Ensure the target subdirectory exists
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                
                # Extract the file content
                with open(dest_path, 'wb') as outfile:
                    outfile.write(zf.read(member))

        print(f"Extraction successful: files extracted directly to {target_directory}.")

    except Exception as e:
        # Provide user feedback on the error
        tk.messagebox.showerror("Extraction Error", f"Failed to extract content: {e}")

# ====================================================================
# NEW MASTER SERVER DEFINITIONS (Added per user request)
# Note: Raw master server addresses (master.jkhub.org) typically return 
# a binary protocol response, not JSON. The code will handle the error 
# if you use these, suggesting you stick to the JSON API.
# ====================================================================

MASTER_SERVERS = {
    "JKHubServers (AppSpot)": "jkhubservers.appspot.com:29070",
    "MBII (master.moviebattles.org)": "master.moviebattles.org:29070",
    "MBII (master2.moviebattles.org)": "master2.moviebattles.org:29070",
    "JKHub (master.jkhub.org)": "master.jkhub.org:29070",
    "Raven Software (masterjk3.ravensoft.com)": "masterjk3.ravensoft.com:29070",
    "Custom URL": ""
}

QUERY_PACKET = b'\xff\xff\xff\xffgetstatus\n'

def ping_server(ip, port, timeout=0.3):
    """
    Pings a Quake 3/JKA server using the standard UDP query protocol 
    to get a more reliable latency measurement.
    """
    try:
        # Use SOCK_DGRAM for UDP
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        
        # 1. Send the query packet
        start_time = time.time()
        sock.sendto(QUERY_PACKET, (ip, port))
        
        # 2. Wait for a response (which includes the ping time implicitly)
        sock.recv(2048) # Read the response packet
        
        end_time = time.time()
        
        # Calculate latency in milliseconds and round it
        latency_ms = round((end_time - start_time) * 1000)
        
        sock.close()
        return latency_ms

    except socket.timeout:
        # A timeout here means the server didn't respond to the official query
        return 999
    except Exception:
        # General error (firewall, routing issue, etc.)
        return -1

def scrape_jkhub_servers(url):
    """
    Scrapes JKHub server list with CORRECT column mapping based on actual table structure:
    Index 0: (empty)
    Index 1: Server Name  
    Index 2: (empty)
    Index 3: Address (IP:Port)
    Index 4: Map
    Index 5: Players  
    Index 6: Bots
    Index 7: Mod
    Index 8: Gametype
    Index 9: Game 
    Index 10: Master Server(s)
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page for scraping: {e}")
        return []

    try:
        soup = BeautifulSoup(response.text, 'lxml')
    except Exception:
        soup = BeautifulSoup(response.text, 'html.parser')

    server_table = soup.find('table')
    if not server_table or not server_table.find('tbody'):
        print("Scraper failed: Could not find server table or table body.")
        return []

    servers = []
    
    for row in server_table.find('tbody').find_all('tr'):
        cells = row.find_all('td')
        if len(cells) < 11:  # Need all 11 columns
            continue

        # CORRECT mapping based on your debug output:
        server_data = {
            'hostname': cells[1].text.strip(),     # Index 1: Server Name
            'addr': cells[3].text.strip(),         # Index 3: Address  
            'mapname': cells[4].text.strip(),      # Index 4: Map
            'clients': cells[5].text.strip(),      # Index 5: Players
            'mod': cells[7].text.strip(),          # Index 7: Mod (this is what we filter on!)
            'gametype': cells[8].text.strip(),     # Index 8: Gametype
            'ping': 'Pinging...'  # Ping data not available in this table, set to N/A
        }

        servers.append(server_data)
        
    print(f"Scraper found {len(servers)} servers")
    
    # Show first 3 servers to verify the mapping
    print("\n=== FIRST 3 SERVERS WITH CORRECT MAPPING ===")
    for i, server in enumerate(servers[:3]):
        print(f"Server {i+1}:")
        print(f"  hostname: '{server.get('hostname')}'")
        print(f"  addr: '{server.get('addr')}'")
        print(f"  mapname: '{server.get('mapname')}'")
        print(f"  clients: '{server.get('clients')}'")
        print(f"  mod: '{server.get('mod')}'")
        print(f"  gametype: '{server.get('gametype')}'")
        print(f"  ping: '{server.get('ping')}'")
        print()
    print("=======================================\n")
    
    return servers



class GitHubReleaseManager:
    """
    A Tkinter application to download a specific release from a GitHub repository.
    This version includes a custom, fully consistent dark theme, handles API rate limiting,
    and now fetches the repository list dynamically on startup from a hardcoded URL.
    It also saves all user-generated files inside a 'cache' folder for better PyInstaller compatibility.
    Crucially, all pop-up windows are now custom-themed to match the main application's aesthetic.
    """

    # NEW: Hardcoded URL for the main repository list file
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
        
        # This instance variable is crucial for preventing the background image
        # from being garbage collected by Python.
        self.bg_image_ref = None
        self.icon_path_ico = None # New instance variable to store the icon path

        # --- Define Colors for a Unified Theme ---
        self.dark_background_color = "#121212"  # A very dark background for consistency
        self.dark_widget_color = "#1e1e1e"     # A slightly lighter dark color for widgets
        self.text_color = "white"
        self.highlight_color = "#4a4a4a"       # A subtle highlight color for selections
        self.border_color = "#333333"          # A darker gray for borders

        # --- File Paths are now relative to a 'cache' directory ---
        self.create_cache_directory()
        self.repositories_file = os.path.join("cache", "repositories.json")
        self.client_file = os.path.join("cache", "client.json")
        self.mbii_directory_file = os.path.join("cache", "mbiidirectory.json")
        # Music file is now expected in the root directory, not the cache
        self.music_file = get_resource_path("music.mp3")
        
        # UI for loading screen
        self.loading_window = None
        self.loading_animation = None
        self.spinner = itertools.cycle(['|', '/', '-', '\\'])
        
        # String variable for the download path display
        self.download_path_var = tk.StringVar(self.master, value="Not Set")
        # String variable for the repository description
        self.description_var = tk.StringVar(self.master, value="Select a repository to see its description.")

        # Initialize the pygame mixer
        mixer.init()

        # Music player state
        self.is_music_playing = False

        self.create_widgets()
        
        # --- NEW STARTUP LOGIC: Fetch repositories first, then populate the UI ---
        self.status_label.config(text="Fetching latest repository list...", fg="#3498db")
        threading.Thread(target=self.fetch_and_populate_repositories, daemon=True).start()

        self.load_mbii_directory()
        self.load_client_data()
        self.load_sound_settings()
        
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
        icon_path_ico = get_resource_path("icon.ico")
        if os.path.exists(icon_path_ico):
            try:
                self.master.iconbitmap(icon_path_ico)
                self.icon_path_ico = icon_path_ico  # Store the path for pop-up windows
            except tk.TclError:
                print("WARNING: 'icon.ico' found but failed to load. Skipping window icon.")
        else:
            try:
                icon_path_png = get_resource_path("icon.png")
                icon_image = Image.open(icon_path_png)
                icon_photo = ImageTk.PhotoImage(icon_image)
                self.master.iconphoto(True, icon_photo)
            except (tk.TclError, FileNotFoundError, IOError):
                print("WARNING: Neither 'icon.ico' nor 'icon.png' found. Skipping window icon.")

        # Create a Canvas that fills the entire master window
        canvas = tk.Canvas(self.master, highlightthickness=0)
        canvas.pack(fill="both", expand=True)

        window_width = 502
        window_height = 351
        
        try:
            image_path = get_resource_path("background.png")
            pil_image = Image.open(image_path)
            resized_image = pil_image.resize((window_width, window_height), Image.LANCZOS)
            self.bg_image_ref = ImageTk.PhotoImage(resized_image)
            canvas.create_image(0, 0, image=self.bg_image_ref, anchor="nw")
            
            # Create a semi-transparent dark overlay on the canvas
            # This is the key to letting the background image show through while maintaining a dark theme.
            canvas.create_rectangle(0, 0, window_width, window_height, fill=self.dark_background_color, stipple='gray50')
            
        except (tk.TclError, FileNotFoundError, IOError):
            print("WARNING: 'background.png' not found or is invalid. Falling back to a solid dark background.")

        # Use a new frame to hold all the content, and place it *on* the canvas
        content_frame = tk.Frame(canvas, bg=self.dark_background_color)
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)
        canvas.create_window(window_width / 2, window_height / 2, window=content_frame, anchor="center")

        # --- Configure a custom ttk style for widgets ---
        style = ttk.Style()
        style.theme_create("CustomDark", parent="alt", settings={
            "TCombobox": {
                "configure": {
                    "selectbackground": self.highlight_color,
                    "fieldbackground": self.dark_widget_color,
                    "background": self.dark_widget_color,
                    "foreground": self.text_color,
                    "bordercolor": self.border_color,
                    "arrowcolor": self.text_color,
                    "padding": 3,
                },
                "map": {
                    "fieldbackground": [("readonly", self.dark_widget_color)],
                    "selectbackground": [("readonly", self.dark_widget_color)],
                    "selectforeground": [("readonly", self.text_color)],
                }
            },
            "TCombobox.listbox": {
                "configure": {
                    "background": self.dark_widget_color,
                    "foreground": self.text_color,
                    "selectbackground": self.highlight_color,
                    "selectforeground": self.text_color,
                    "bordercolor": self.border_color,
                    "relief": "flat",
                }
            },
            "TLabel": {
                "configure": {
                    "background": self.dark_background_color,
                    "foreground": self.text_color,
                }
            },
            "TFrame": {
                "configure": {
                    "background": self.dark_background_color,
                }
            },
            # A new style for the download path entry with a light background and dark text
            "DownloadPath.TEntry": {
                "configure": {
                    "fieldbackground": "#f0f0f0",  # Light gray background
                    "foreground": "black",         # Black text
                    "bordercolor": self.border_color,
                },
                "map": {
                    "fieldbackground": [("readonly", "#f0f0f0")],
                }
            },
            "TButton": {
                "configure": {
                    "background": self.border_color,
                    "foreground": self.text_color,
                    "bordercolor": self.border_color,
                    "relief": "flat",
                },
                "map": {
                    "background": [("active", self.highlight_color)],
                }
            },
            "TScrollbar": {
                "configure": {
                    "background": self.border_color,
                    "troughcolor": self.dark_widget_color,
                    "bordercolor": self.border_color,
                }
            },
        })
        style.theme_use("CustomDark")

        # --- NEW: Top Button Row for App Sections ---
        top_button_frame = tk.Frame(content_frame, bg=self.dark_background_color)
        # Use column 0, span 2 columns, at the very top (row 0)
        top_button_frame.grid(row=0, column=0, columnspan=2, pady=(10, 5), sticky="ew")
        
        # Function to handle button clicks (for now, just a placeholder)
        def placeholder_action(button_name):
            self.show_custom_messagebox(
                f"{button_name} Feature",
                f"The '{button_name}' feature is not yet implemented in this version.",
                icon_type='info'
            )

        def no_action(button_name):
            """A function that executes, but performs no operation."""
            pass

        # Content Button
        self.content_button = tk.Button(top_button_frame, text="Content", command=lambda: no_action("Content"), bg=self.border_color, fg=self.text_color, activebackground=self.highlight_color, relief="raised", font=("Helvetica", 9, "bold"))
        self.content_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # Server Browser Button (UPDATED to call the new method)
        self.server_browser_button = tk.Button(top_button_frame, text="Server Browser", command=self.open_server_browser, bg=self.border_color, fg=self.text_color, activebackground=self.highlight_color, relief="raised", font=("Helvetica", 9, "bold"))
        self.server_browser_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        # --- END NEW BUTTONS ---


        # Saved Repositories Listbox Section
        # NOTE: All subsequent row indices must be incremented by 1 due to the new row 0.
        list_frame = tk.LabelFrame(content_frame, text="Community Content", padx=5, pady=5, bg=self.dark_background_color, fg=self.text_color, borderwidth=1, relief="flat")
        list_frame.grid(row=1, column=0, columnspan=2, pady=5, sticky="ew")
        list_frame.grid_columnconfigure(0, weight=1)
        
        scrollbar = tk.Scrollbar(list_frame, background=self.border_color, troughcolor=self.dark_widget_color, activebackground=self.highlight_color)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox_repos = tk.Listbox(list_frame, height=6, yscrollcommand=scrollbar.set, font=("Helvetica", 9), bg=self.dark_widget_color, fg=self.text_color, selectbackground=self.highlight_color, highlightthickness=0, relief="flat")
        self.listbox_repos.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.listbox_repos.bind("<<ListboxSelect>>", self.on_listbox_select)
        scrollbar.config(command=self.listbox_repos.yview)
        
        # Repository Description Label
        self.description_label = tk.Label(content_frame, textvariable=self.description_var, wraplength=480, justify=tk.CENTER, bg=self.dark_background_color, fg=self.text_color, font=("Helvetica", 9, "italic"))
        self.description_label.grid(row=2, column=0, columnspan=2, pady=(3,0), sticky="ew")

        # Separator
        tk.Frame(content_frame, height=2, bg=self.border_color).grid(row=3, column=0, columnspan=2, pady=5, sticky="ew")

        # Release Version Dropdown
        self.label_release = tk.Label(content_frame, text="Select a Release Version:", bg=self.dark_background_color, fg=self.text_color, font=("Helvetica", 9, "bold"))
        self.label_release.grid(row=4, column=0, padx=5, pady=(3,0), sticky="e")

        self.release_version_combo = ttk.Combobox(content_frame, style="TCombobox", state="disabled", width=37)
        self.release_version_combo.grid(row=4, column=1, padx=5, pady=(3,0), sticky="w")
        self.release_version_combo['values'] = ['Please select a repository...']
        self.release_version_combo.set('Please select a repository...')
        self.release_version_combo.bind("<<ComboboxSelected>>", self.on_release_version_select)

        # Download Path Section
        self.download_path_label = tk.Label(content_frame, text="MBII Folder Path:", bg=self.dark_background_color, fg=self.text_color, font=("Helvetica", 9, "bold"))
        self.download_path_label.grid(row=5, column=0, padx=5, pady=3, sticky="e")
        
        path_button_frame = tk.Frame(content_frame, bg=self.dark_background_color)
        path_button_frame.grid(row=5, column=1, padx=5, pady=3, sticky="w")
        
        # Use the new style for the Entry widget
        self.download_path_display = ttk.Entry(path_button_frame, textvariable=self.download_path_var, width=30, state="readonly", style="DownloadPath.TEntry")
        self.download_path_display.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.download_path_button = tk.Button(path_button_frame, text="Browse", command=self.select_download_path, bg=self.border_color, fg=self.text_color, activebackground=self.highlight_color, relief="raised")
        self.download_path_button.pack(side=tk.LEFT)
        
        # Status Label and Buttons
        self.status_label = tk.Label(content_frame, text="", bg=self.dark_background_color, fg="#3498db")
        self.status_label.grid(row=6, column=0, columnspan=2, pady=(3, 2), sticky="ew")
        
        self.button_frame = tk.Frame(content_frame, bg=self.dark_background_color)
        self.button_frame.grid(row=7, column=0, columnspan=2, pady=(2, 0))

        self.download_button = tk.Button(self.button_frame, text="Download", state="disabled", command=self.on_download, bg="#4CAF50", fg=self.text_color, activebackground="#45a049", relief="raised", font=("Helvetica", 9, "bold"))
        self.download_button.pack(side=tk.LEFT, padx=5)
        self.download_button.bind("<Enter>", lambda e: e.widget.configure(bg="#45a049"))
        self.download_button.bind("<Leave>", lambda e: e.widget.configure(bg="#4CAF50"))

        self.remove_button = tk.Button(self.button_frame, text="Remove", state="disabled", command=self.on_remove, bg="#e74c3c", fg=self.text_color, activebackground="#c0392b", relief="raised", font=("Helvetica", 9, "bold"))
        self.remove_button.pack(side=tk.LEFT, padx=5)
        self.remove_button.bind("<Enter>", lambda e: e.widget.configure(bg="#c0392b"))
        self.remove_button.bind("<Leave>", lambda e: e.widget.configure(bg="#e74c3c"))
        
        self.music_button = tk.Button(self.button_frame, text="Music Off", command=self.toggle_music, bg="#3498db", fg=self.text_color, activebackground="#2980b9", relief="raised", font=("Helvetica", 9, "bold"))
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
            self.show_custom_messagebox(
                "Rate Limit Exceeded",
                "Refreshed due to being rate limited, please wait approximately one minute.",
                icon_type='warning'
            )
            self.master.quit()

    def fetch_and_populate_repositories(self):
        """
        Fetches the repository list from the hardcoded URL.
        If that fails, it falls back to a local file in the cache directory.
        The UI is then populated on the main thread.
        """
        try:
            url = self.HARDCODED_REPOSITORIES_REPO_URL
            response = requests.get(url)
            response.raise_for_status()
            
            self.repositories = response.json()
            
            # Save the newly fetched list for local fallback
            try:
                with open(self.repositories_file, 'w') as f:
                    json.dump(self.repositories, f, indent=4)
            except IOError as e:
                self.master.after(0, lambda: self.show_custom_messagebox("File Save Error", f"Could not save the new repository list: {e}", icon_type='warning'))
            
            self.master.after(0, lambda: self.status_label.config(text="Loaded repository list from remote URL.", fg="#4CAF50"))
            self.master.after(0, self.populate_repositories)

        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            # Fallback to local file if the remote fetch fails
            if os.path.exists(self.repositories_file):
                try:
                    with open(self.repositories_file, 'r') as f:
                        self.repositories = json.load(f)
                    self.master.after(0, lambda: self.status_label.config(text="Could not fetch remote list. Loaded local fallback.", fg="orange"))
                except (IOError, json.JSONDecodeError):
                    self.repositories = []
                    self.master.after(0, lambda: self.status_label.config(text="Failed to load local repositories file. Please check your network.", fg="#e74c3c"))
            else:
                self.repositories = []
                self.master.after(0, lambda: self.status_label.config(text="No remote or local repository list found. Please check network.", fg="#e74c3c"))
                # Capture 'e' with a default argument 'msg'
                self.master.after(0, lambda msg=str(e): self.show_custom_messagebox("Repository List Warning", f"Could not fetch or find repositories.json.\nError: {msg}", icon_type='warning'))

            self.master.after(0, self.populate_repositories)

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
            self.show_custom_messagebox("Error", f"Could not save client data to file: {e}", icon_type='error')

    def save_music_settings(self):
        """Saves the current music settings to client_data and then to the file."""
        music_settings = self.client_data.get("music_settings", {})
        music_settings["auto_play"] = self.is_music_playing
        music_settings["volume"] = mixer.music.get_volume() if mixer.get_init() else 0.16
        self.client_data["music_settings"] = music_settings
        self.save_client_data()

    def load_sound_settings(self):
        """Loads sound settings from `client.json` or uses defaults."""
        music_settings = self.client_data.get("music_settings", {})
        auto_play = music_settings.get("auto_play", True)
        volume = music_settings.get("volume", 0.16)
        
        # --- CRITICAL FIX: Explicitly set the internal state first ---
        self.is_music_playing = auto_play 

        if mixer.get_init():
            mixer.music.set_volume(max(0, min(1, volume)))
            
            # Load the music file, regardless of whether it's playing
            if os.path.exists(self.music_file):
                try:
                    mixer.music.load(self.music_file)
                except mixer.error as e:
                    print(f"Failed to load music file on startup: {e}")
                    self.is_music_playing = False
                    
            # ONLY start playback if auto_play was True
            if self.is_music_playing:
                try:
                    mixer.music.play(-1)
                except mixer.error:
                    self.is_music_playing = False
            else:
                # If music should be off, ensure the mixer is stopped
                mixer.music.stop()

            # --- Set the button text to reflect the final determined state ---
            if self.is_music_playing:
                self.music_button.config(text="Music On")
            else:
                self.music_button.config(text="Music Off")

    def play_music(self):
        """Plays the music.mp3 file if it exists."""
        if os.path.exists(self.music_file):
            try:
                mixer.music.load(self.music_file)
                mixer.music.play(-1)
                self.is_music_playing = True
                self.music_button.config(text="Music On")
                # self.save_music_settings() # <--- REMOVED: This was causing the save loop on startup
            except mixer.error as e:
                self.show_custom_messagebox("Music Error", f"Failed to play music file: {e}", icon_type='error')
                self.is_music_playing = False
                self.music_button.config(text="Music Off")
        else:
            self.is_music_playing = False
            self.music_button.config(text="Music Off")
            self.show_custom_messagebox("File Not Found", f"Music file '{self.music_file}' not found.", icon_type='warning')

    def toggle_music(self):
        """Toggles music playback on and off."""
        if self.is_music_playing:
            mixer.music.pause()
            self.is_music_playing = False  # <-- Sets internal state to False
            self.music_button.config(text="Music Off")
        else:
            if mixer.music.get_busy():
                mixer.music.unpause()
            else:
                self.play_music()
            self.is_music_playing = True   # <-- Sets internal state to True
            self.music_button.config(text="Music On")
        
        self.save_music_settings()  # <-- Calls the function to save the new state

    def load_mbii_directory(self):
        """ Loads the MBII directory from a local JSON file. """
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
            self.show_custom_messagebox("Error", f"Could not save MBII directory to file: {e}", icon_type='error')

    def populate_repositories(self):
        """ Clears and repopulates the Listbox with the current repositories. The color of each item is based on the status of the last downloaded tag: - Green: up-to-date - Red: outdated - Orange: processing (until checked) - White: untouched / unknown """
        self.listbox_repos.delete(0, tk.END)
        for i, repo in enumerate(self.repositories):
            repo_name_display = repo.get('custom_name') or repo['url'].rstrip('/').split('/')[-1]
            self.listbox_repos.insert(tk.END, repo_name_display)
            url = repo.get('url')
            last_tag = self.client_data.get(url, {}).get('last_tag')
            # Default to white
            color = "white"
            if last_tag:
                # Temporarily mark as processing (orange)
                color = "orange"
                self.listbox_repos.itemconfig(i, {'fg': color})
                
                def update_color(index, repo_url, tag):
                    try:
                        parts = repo_url.rstrip('/').split('/')
                        owner = parts[-2]
                        repo_name = parts[-1]
                        api_url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/latest"
                        response = requests.get(api_url)
                        response.raise_for_status()
                        latest = response.json().get('tag_name')
                        new_color = "green" if latest == tag else "red"
                    except:
                        new_color = "white"
                    self.master.after(0, lambda idx=i, new_c=new_color: self.listbox_repos.itemconfig(idx, {'fg': new_c}))
                
                # Launch the check in a thread to avoid freezing the GUI
                threading.Thread(target=update_color, args=(i, url, last_tag), daemon=True).start()
            else:
                self.listbox_repos.itemconfig(i, {'fg': color})
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
                self.show_custom_messagebox("Invalid Directory", "The selected directory must contain 'MBII' in its name.", icon_type='error')
                self.download_path = None
                self.download_path_var.set("Not Set")
        self.update_download_button_state()

    def on_listbox_select(self, event):
        """ Handles a repository selection, fetching its releases in a new thread. This is where the API call and rate-limit check now occur. """
        if self.is_rate_limited: return
        selection = self.listbox_repos.curselection()
        if not selection and self.selected_repo_url is not None: return
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
                self.show_custom_messagebox("Error", f"Invalid repository URL format for '{self.selected_repo_url}'.", icon_type='error')
                self.reset_ui()
                self.selected_repo_url = None
                return
            self.status_label.config(text="Fetching releases...", fg="#3498db")
            self.update_download_button_state()
            self.update_remove_button_state()
            # Fetch releases in a new thread to prevent the UI from freezing
            threading.Thread(target=self.fetch_releases, daemon=True).start()
        else:
            self.reset_ui()
        
    def fetch_releases(self):
        """ Fetches the releases for the currently selected repository. """
        if not self.selected_repo_url: return
        try:
            api_url = f"https://api.github.com/repos/{self.current_owner}/{self.current_repo}/releases"
            response = requests.get(api_url)
            
            if response.status_code == 403 and 'rate limit' in response.text.lower():
                return self.master.after(0, self.handle_rate_limit)

            response.raise_for_status()
            releases = response.json()
            
            self.available_releases = {}
            for release in releases:
                tag = release.get('tag_name')
                asset_url = next((asset['browser_download_url'] for asset in release.get('assets', []) if asset['name'].endswith(('.zip', '.pk3'))), None)
                if tag and asset_url:
                    self.available_releases[tag] = asset_url

            self.master.after(0, self.populate_release_combo)

        except requests.exceptions.RequestException as e:
            # FIX: Capture 'e' using default argument 'error=e'
            self.master.after(0, lambda error=e: self.status_label.config(text=f"Failed to fetch releases: {error}", fg="#e74c3c"))
            self.master.after(0, self.reset_ui)

    def populate_release_combo(self):
        """ Populates the release version combobox and selects the latest or previously downloaded version. """
        tags = list(self.available_releases.keys())
        if not tags:
            self.release_version_combo['values'] = ['No releases found']
            self.release_version_combo.set('No releases found')
            self.release_version_combo.config(state="disabled")
            self.status_label.config(text="No downloadable releases found.", fg="orange")
            self.selected_release_tag = None
        else:
            self.release_version_combo['values'] = tags
            last_tag = self.client_data.get(self.selected_repo_url, {}).get('last_tag')
            
            # Select the latest tag by default
            selected_tag = tags[0]
            
            # If the last downloaded tag is still available, select it
            if last_tag in tags:
                selected_tag = last_tag
                
            self.release_version_combo.set(selected_tag)
            self.selected_release_tag = selected_tag
            self.release_version_combo.config(state="readonly")
            self.status_label.config(text=f"Ready. Selected: {selected_tag}", fg="#4CAF50")
            
        self.update_download_button_state()

    def on_release_version_select(self, event):
        """ Handles a release version selection. """
        self.selected_release_tag = self.release_version_combo.get()
        self.status_label.config(text=f"Selected: {self.selected_release_tag}", fg="#4CAF50")
        self.update_download_button_state()

    def update_download_button_state(self):
        """ Updates the state of the Download button. """
        if self.download_path and self.selected_release_tag and self.selected_release_tag not in ["Loading releases...", "No releases found"]:
            self.download_button.config(state="normal")
        else:
            self.download_button.config(state="disabled")

    def update_remove_button_state(self):
        """ Updates the state of the Remove button. """
        if self.download_path and self.selected_repo_url:
            last_tag = self.client_data.get(self.selected_repo_url, {}).get('last_tag')
            if last_tag:
                self.remove_button.config(state="normal")
                return
        self.remove_button.config(state="disabled")

    def reset_ui(self):
        """ Resets the UI elements to their default state after a selection or error. """
        self.release_version_combo.set('Please select a repository...')
        self.release_version_combo.config(state="disabled")
        self.description_var.set("Select a repository to see its description.")
        self.selected_release_tag = None
        self.update_download_button_state()
        self.update_remove_button_state()
        
    def on_download(self):
        """ Initiates the download process in a new thread. """
        if not self.download_path:
            self.show_custom_messagebox("Error", "Please select your MBII folder path first.", icon_type='error')
            return
        if not self.selected_release_tag:
            self.show_custom_messagebox("Error", "Please select a release version.", icon_type='error')
            return
            
        download_url = self.available_releases.get(self.selected_release_tag)
        if not download_url:
            self.show_custom_messagebox("Error", f"Could not find download URL for tag {self.selected_release_tag}.", icon_type='error')
            return

        self.show_loading_popup()
        self.download_button.config(state="disabled")
        threading.Thread(target=self._download_thread, args=(download_url,), daemon=True).start()

    def _download_thread(self, url):
        """ The actual download and extraction logic. """
        try:
            #self.master.after(0, lambda: self.loading_label.config(text="Downloading file..."))
            response = requests.get(url, stream=True)
            response.raise_for_status()

            filename = url.split('/')[-1]
            mod_folder = os.path.join(self.download_path, self.current_repo)
            
            # Ensure the mod directory exists for extraction
            os.makedirs(mod_folder, exist_ok=True)
            
            download_dir = os.path.join(self.download_path)

            # Check if the file is a PK3 (single file) or a ZIP (archive)
            if filename.lower().endswith(".pk3"):
                # PK3: Save directly to the mod directory
                filepath = os.path.join(download_dir, filename)
                self.master.after(0, lambda: self.loading_label.config(text=f"Saving {filename} to {download_dir}..."))
                with open(filepath, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        file.write(chunk)
                
                # Check for existing pk3 and remove
                self.remove_previous_file(download_dir, filename)

                self.master.after(0, self.hide_loading_popup)
                self.master.after(0, lambda: self.show_custom_messagebox("Success", f"Successfully downloaded and saved {filename}.", icon_type='info'))

            elif filename.lower().endswith(".zip"):
                # ZIP: Extract contents to the download directory
                #self.master.after(0, lambda: self.loading_label.config(text="Extracting ZIP archive..."))

                extract_zip_contents(response.content, download_dir)

                self.master.after(0, self.hide_loading_popup)
                self.master.after(0, lambda: self.show_custom_messagebox("Success", f"Successfully downloaded and extracted {filename} to {download_dir}.", icon_type='info'))

            else:
                self.master.after(0, self.hide_loading_popup)
                self.master.after(0, lambda: self.show_custom_messagebox("Error", f"Unsupported file type: {filename}. Only .zip and .pk3 are supported.", icon_type='error'))
                return

            # Update client data on successful download
            self.client_data[self.selected_repo_url] = {
                'last_tag': self.selected_release_tag,
                'last_file': filename,
                'path': download_dir
            }
            self.save_client_data()
            self.master.after(0, self.populate_repositories) # Refresh colors in main listbox

        except requests.exceptions.RequestException as e:
            self.master.after(0, self.hide_loading_popup)
            # FIX: Capture 'e' using default argument 'error=e'
            self.master.after(0, lambda error=e: self.show_custom_messagebox("Download Error", f"Failed to download file: {error}", icon_type='error'))
        except Exception as e:
            self.master.after(0, self.hide_loading_popup)
            # FIX: Capture 'e' using default argument 'error=e'
            self.master.after(0, lambda error=e: self.show_custom_messagebox("Extraction Error", f"An error occurred during file handling: {error}", icon_type='error'))
        finally:
            self.master.after(0, lambda: self.download_button.config(state="normal"))
            self.master.after(0, self.update_download_button_state)

    def remove_previous_file(self, target_dir, new_filename):
        """ Removes the previously downloaded file/folder if a new one is a single PK3."""
        # This is primarily for PK3 files where only one version should exist.
        if new_filename.lower().endswith('.pk3'):
            last_file = self.client_data.get(self.selected_repo_url, {}).get('last_file')
            if last_file and last_file != new_filename:
                old_filepath = os.path.join(target_dir, last_file)
                if os.path.exists(old_filepath):
                    try:
                        os.remove(old_filepath)
                    except OSError as e:
                        print(f"Warning: Could not remove old file {old_filepath}: {e}")
            
    def on_remove(self):
        """ Prompts the user and removes the last downloaded content. """
        if not self.selected_repo_url or not self.download_path:
            return

        repo_info = self.client_data.get(self.selected_repo_url, {})
        last_tag = repo_info.get('last_tag')
        last_file = repo_info.get('last_file')
        mod_path = repo_info.get('path')
        
        if not last_tag or not mod_path:
            self.show_custom_messagebox("Error", "No prior download record found to remove.", icon_type='error')
            self.update_remove_button_state()
            return
            
        repo_name = self.current_repo_data.get('custom_name') or self.current_repo
        
        if last_file and last_file.lower().endswith('.pk3'):
            # PK3: remove single file
            removal_target = os.path.join(mod_path, last_file)
            message = f"Are you sure you want to remove the single file **{last_file}** for **{repo_name}** from **{mod_path}**?"
            is_file = True
        else:
            # ZIP: remove the entire directory (assuming ZIPs extract to a folder named after the repo)
            removal_target = mod_path
            message = f"Are you sure you want to remove the entire content folder for **{repo_name}** at **{mod_path}**? This will delete the entire directory."
            is_file = False
            
        # Use a custom confirmation dialog
        if self.show_custom_confirmation("Confirm Removal", message):
            self.remove_button.config(state="disabled")
            threading.Thread(target=self._remove_thread, args=(removal_target, is_file), daemon=True).start()
            
    def _remove_thread(self, target, is_file):
        """ Executes the removal process. """
        try:
            if os.path.exists(target):
                if is_file:
                    os.remove(target)
                else:
                    shutil.rmtree(target)
            
            # Clear the record from client data
            if self.selected_repo_url in self.client_data:
                del self.client_data[self.selected_repo_url]
                self.save_client_data()
                
            self.master.after(0, lambda: self.show_custom_messagebox("Success", f"Successfully removed content: {os.path.basename(target)}", icon_type='info'))
            self.master.after(0, self.populate_repositories) # Refresh colors
            
        except OSError as e:
            self.master.after(0, lambda error=e: self.show_custom_messagebox("Removal Error", f"Failed to remove content: {error}", icon_type='error'))
        finally:
            self.master.after(0, self.update_remove_button_state)

    def show_loading_popup(self):
        """ Creates a custom loading popup window. """
        self.loading_window = tk.Toplevel(self.master)
        self.loading_window.title("Downloading...")
        self.loading_window.geometry("300x100")
        self.loading_window.configure(bg=self.dark_background_color)
        self.loading_window.resizable(False, False)
        self.loading_window.grab_set()
        
        # Set the icon for the pop-up window
        if self.icon_path_ico:
            self.loading_window.iconbitmap(self.icon_path_ico)
            
        # Center the popup relative to the main window
        x = self.master.winfo_x() + self.master.winfo_width() // 2 - 150
        y = self.master.winfo_y() + self.master.winfo_height() // 2 - 50
        self.loading_window.geometry(f'+{x}+{y}')

        tk.Label(self.loading_window, text="Downloading release...", font=("Helvetica", 12), bg=self.dark_background_color, fg=self.text_color).pack(pady=10)
        self.loading_label = tk.Label(self.loading_window, text=" | ", font=("Helvetica", 16, "bold"), bg=self.dark_background_color, fg=self.text_color)
        self.loading_label.pack(pady=5)
        
        self.update_spinner()
    
    def update_spinner(self):
        """Updates the spinner text on the loading label."""
        if self.loading_window and self.loading_window.winfo_exists():
            next_frame = next(self.spinner)
            self.loading_label.config(text=f" {next_frame} ")
            self.loading_window.after(100, self.update_spinner)
    
    def hide_loading_popup(self):
        """ Destroys the custom loading popup. """
        if self.loading_window and self.loading_window.winfo_exists():
            self.loading_window.destroy()

    def show_custom_messagebox(self, title, message, icon_type='info', parent=None):
        """ Creates a custom themed message box. """
        parent_window = parent if parent else self.master
        message_window = tk.Toplevel(parent_window)
        message_window.title(title)
        message_window.configure(bg=self.dark_background_color)
        message_window.resizable(False, False)
        message_window.grab_set()
        
        if self.icon_path_ico:
            message_window.iconbitmap(self.icon_path_ico)
            
        # Icon representation
        icon_map = {'info': 'ℹ️', 'warning': '⚠️', 'error': '❌'}
        icon = icon_map.get(icon_type, '❓')
        
        # Icon Frame
        icon_frame = tk.Frame(message_window, bg=self.dark_background_color)
        icon_frame.pack(padx=15, pady=15, fill="x")
        
        tk.Label(icon_frame, text=icon, font=("Helvetica", 18), bg=self.dark_background_color).pack(side=tk.LEFT, padx=(0, 10))
        
        # Message Label
        tk.Label(icon_frame, text=message, wraplength=350, justify=tk.LEFT, bg=self.dark_background_color, fg=self.text_color).pack(side=tk.LEFT, fill="x", expand=True)
        
        # OK Button
        ok_button = tk.Button(message_window, text="OK", command=message_window.destroy, bg=self.border_color, fg=self.text_color, activebackground=self.highlight_color, relief="raised", font=("Helvetica", 10, "bold"))
        ok_button.pack(pady=(0, 10), padx=10)
        message_window.bind('<Return>', lambda event=None: message_window.destroy())
        
        # Calculate approximate centered position
        message_window.update_idletasks()
        w = message_window.winfo_reqwidth()
        h = message_window.winfo_reqheight()
        x = parent_window.winfo_x() + parent_window.winfo_width() // 2 - w // 2
        y = parent_window.winfo_y() + parent_window.winfo_height() // 2 - h // 2
        message_window.geometry(f'+{x}+{y}')
        
        message_window.transient(parent_window)
        message_window.wait_window()
        
    def show_custom_confirmation(self, title, message):
        """ Creates a custom themed confirmation box (Yes/No). """
        result = tk.BooleanVar(self.master, value=False)
        
        confirm_window = tk.Toplevel(self.master)
        confirm_window.title(title)
        confirm_window.configure(bg=self.dark_background_color)
        confirm_window.resizable(False, False)
        confirm_window.grab_set()
        
        if self.icon_path_ico:
            confirm_window.iconbitmap(self.icon_path_ico)
            
        def on_yes():
            result.set(True)
            confirm_window.destroy()
            
        def on_no():
            result.set(False)
            confirm_window.destroy()

        # Icon and Message Frame
        msg_frame = tk.Frame(confirm_window, bg=self.dark_background_color)
        msg_frame.pack(padx=15, pady=15, fill="x")
        
        tk.Label(msg_frame, text="❓", font=("Helvetica", 18), bg=self.dark_background_color).pack(side=tk.LEFT, padx=(0, 10))
        tk.Label(msg_frame, text=message, wraplength=350, justify=tk.LEFT, bg=self.dark_background_color, fg=self.text_color).pack(side=tk.LEFT, fill="x", expand=True)

        # Button Frame
        button_frame = tk.Frame(confirm_window, bg=self.dark_background_color)
        button_frame.pack(pady=(0, 10), padx=10)
        
        yes_button = tk.Button(button_frame, text="Yes", command=on_yes, bg="#e74c3c", fg=self.text_color, activebackground="#c0392b", relief="raised", font=("Helvetica", 10, "bold"))
        yes_button.pack(side=tk.LEFT, padx=5)
        
        no_button = tk.Button(button_frame, text="No", command=on_no, bg=self.border_color, fg=self.text_color, activebackground=self.highlight_color, relief="raised", font=("Helvetica", 10, "bold"))
        no_button.pack(side=tk.LEFT, padx=5)
        
        # Center the popup
        confirm_window.update_idletasks()
        w = confirm_window.winfo_reqwidth()
        h = confirm_window.winfo_reqheight()
        x = self.master.winfo_x() + self.master.winfo_width() // 2 - w // 2
        y = self.master.winfo_y() + self.master.winfo_height() // 2 - h // 2
        confirm_window.geometry(f'+{x}+{y}')
        
        confirm_window.transient(self.master)
        confirm_window.wait_window()
        
        return result.get()

    def open_server_browser(self):
        """Opens the Server Browser window."""
        ServerBrowser(self.master, self.show_custom_messagebox, self.icon_path_ico, 
                      self.dark_background_color, self.text_color, self.dark_widget_color, 
                      self.highlight_color, self.border_color)

# ====================================================================
# NEW: ServerBrowser Class (Implements the server list logic)
# ====================================================================

class ServerBrowser:
    def __init__(self, master, custom_messagebox_func, icon_path_ico, dark_bg, text_color, widget_color, highlight_color, border_color):

        self.mod_name_map = {
            'Movie Battles II': [
                'movie battles',
                'moviebattles',
                'Movie Battles',
                'mb2',  # Adding shorter variants
                'mbii'
            ],
            'basejk': ['basejk', 'basejka', 'base'],
            'OpenJK': ['openjk', 'ojk'],
            'All Mods': ['']
        }

        self.master = master
        self.show_custom_messagebox = custom_messagebox_func
        self.icon_path_ico = icon_path_ico
        
        # Style variables
        self.dark_background_color = dark_bg
        self.text_color = text_color
        self.dark_widget_color = widget_color
        self.highlight_color = highlight_color
        self.border_color = border_color
        
        # State variables
        self.current_master_url = MASTER_SERVERS["JKHubServers (AppSpot)"]
        self.servers = []
        self.filter_popup = None
        self.mod_filter = 'Movie Battles II'  # Start with All Mods to see everything first
        
        # UI Setup
        self.window = tk.Toplevel(self.master)
        self.window.title("MBII Server Browser")
        self.window.geometry("1200x600")  # Made even wider
        self.window.configure(bg=self.dark_background_color)
        
        if self.icon_path_ico:
            self.window.iconbitmap(self.icon_path_ico)
            
        self.create_widgets()
        self.fetch_servers()
        self.setup_sorting()

    def _sanitize_string(self, text):
        """Removes non-alphanumeric characters and converts to lowercase."""
        if not isinstance(text, str):
            return ""

        text = text.lower()
        text = text.replace('\xa0', ' ').replace('\u2003', ' ')
        text = re.sub(r'[^a-z0-9 ]', '', text) 
        return ' '.join(text.split()).strip()

    def sort_column(self, col, reverse):
        """Sorts Treeview contents when a column header is clicked."""
        import sys

        l = [(self.server_tree.set(k, col), k) for k in self.server_tree.get_children('')]
        is_numeric = col in ('Ping', 'Players')
        
        if is_numeric:
            def sort_key(item):
                value = item[0]
                if isinstance(value, str):
                    try:
                        return int(''.join(filter(str.isdigit, value)) or sys.maxsize)
                    except ValueError:
                        return sys.maxsize
                return value
            l.sort(key=sort_key, reverse=reverse)
        else:
            l.sort(key=lambda t: t[0].lower(), reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.server_tree.move(k, '', index)

        self.server_tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def setup_sorting(self):
        """Binds the sorting function to the relevant column headers."""
        sortable_columns = ['Name', 'Address', 'Map', 'Players', 'Mod', 'GameType', 'Ping'] 
        
        for col in sortable_columns:
            if col in self.server_tree["columns"]:
                self.server_tree.heading(col, command=lambda c=col: self.sort_column(c, False))

    def create_widgets(self):
        # Configure the Ttk Treeview Style for Dark Theme
        style = ttk.Style(self.window)
        style.theme_use("default")

        style.configure("Dark.Treeview", 
                        background=self.dark_widget_color,
                        foreground=self.text_color, 
                        fieldbackground=self.dark_widget_color,
                        rowheight=25,
                        font=('Helvetica', 9))  # Smaller font to fit more
                        
        style.map('Dark.Treeview', 
                  background=[('selected', self.highlight_color)],
                  foreground=[('selected', self.text_color)])
                  
        style.configure("Dark.Treeview.Heading", 
                        background=self.border_color,
                        foreground=self.text_color,
                        font=('Helvetica', 9, 'bold'))
        style.map("Dark.Treeview.Heading", 
                  background=[('active', self.highlight_color)])

        # Main Frame Setup
        main_frame = tk.Frame(self.window, bg=self.dark_background_color)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # Server List Frame Setup
        list_frame = tk.Frame(main_frame, bg=self.dark_widget_color)
        list_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)
        
        # Define the columns
        all_columns = ('Name', 'Address', 'Map', 'Players', 'Mod', 'GameType', 'Ping')
        
        # Scrollbars
        list_vscrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, 
                                       bg=self.border_color, troughcolor=self.dark_widget_color)
        list_vscrollbar.grid(row=0, column=1, sticky="ns")

        list_hscrollbar = tk.Scrollbar(list_frame, orient=tk.HORIZONTAL,
                                       bg=self.border_color, troughcolor=self.dark_widget_color)
        list_hscrollbar.grid(row=1, column=0, sticky="ew") 
        
        # Treeview setup
        self.server_tree = ttk.Treeview(
            list_frame, 
            columns=all_columns, 
            show='headings', 
            yscrollcommand=list_vscrollbar.set,
            xscrollcommand=list_hscrollbar.set,
            style="Dark.Treeview"
        )

        list_vscrollbar.config(command=self.server_tree.yview)
        list_hscrollbar.config(command=self.server_tree.xview)
        self.server_tree.grid(row=0, column=0, sticky="nsew") 

        # Define column properties with better widths
        self.server_tree.heading('Name', text='Server Name ↕', anchor=tk.W)
        self.server_tree.column('Name', width=250, stretch=tk.NO, anchor=tk.W) 
        
        self.server_tree.heading('Address', text='IP:Port ↕', anchor=tk.W)
        self.server_tree.column('Address', width=130, stretch=tk.NO, anchor=tk.W) 
        
        self.server_tree.heading('Map', text='Map ↕', anchor=tk.W)
        self.server_tree.column('Map', width=120, stretch=tk.NO, anchor=tk.W)
        
        self.server_tree.heading('Players', text='Players ↕', anchor=tk.CENTER)
        self.server_tree.column('Players', width=70, stretch=tk.NO, anchor=tk.CENTER)

        self.server_tree.heading('Mod', text='Mod ↕', anchor=tk.W)
        self.server_tree.column('Mod', width=120, stretch=tk.NO, anchor=tk.W)

        self.server_tree.heading('GameType', text='Game Type ↕', anchor=tk.W)
        self.server_tree.column('GameType', width=100, stretch=tk.NO, anchor=tk.W)

        self.server_tree.heading('Ping', text='Ping ↕', anchor=tk.CENTER)
        self.server_tree.column('Ping', width=50, stretch=tk.NO, anchor=tk.CENTER)

        # Status and Control Frame
        control_frame = tk.Frame(self.window, bg=self.dark_background_color)
        control_frame.pack(fill="x", padx=5, pady=5)
        control_frame.grid_columnconfigure(0, weight=1)
        
        self.status_label = tk.Label(control_frame, text="Ready.", bg=self.dark_background_color, fg=self.text_color, anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")
        
        button_frame = tk.Frame(control_frame, bg=self.dark_background_color)
        button_frame.grid(row=0, column=1, sticky="e")

        self.filter_button = tk.Button(button_frame, text="Filter", command=self.open_filter_popup, 
                                      bg=self.border_color, fg=self.text_color, 
                                      activebackground=self.highlight_color, relief="raised")
        self.filter_button.pack(side=tk.LEFT, padx=5)
        
        self.refresh_button = tk.Button(button_frame, text="Refresh", command=self.fetch_servers, 
                                       bg=self.border_color, fg=self.text_color, 
                                       activebackground=self.highlight_color, relief="raised")
        self.refresh_button.pack(side=tk.LEFT, padx=5)

    def fetch_servers(self):
        self.status_label.config(text=f"Fetching servers...", fg="#3498db")
        self.refresh_button.config(state="disabled")
        self.filter_button.config(state="disabled")
        threading.Thread(target=self._fetch_servers_thread, daemon=True).start()

    def _fetch_servers_thread(self):
        """Fetch servers with diagnostic output"""
        JKHUB_SCRAPER_URL = "https://jkhubservers.appspot.com"
        MAX_PING_THREADS = 20 # Limit the number of concurrent pings

        try:
            print("Using diagnostic web scraper...")
            new_servers = scrape_jkhub_servers(JKHUB_SCRAPER_URL)
            
            # --- Step 2: PARALLEL PINGING LOOP ---
            # Use a ThreadPoolExecutor to run ping_server for many servers at once.
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PING_THREADS) as executor:
                future_to_server = {}
                
                # 1. Submit ping tasks to the pool
                for server in new_servers:
                    addr = server.get('addr')
                    ip, port = None, None
                    
                    if ':' in addr:
                        try:
                            # Extract IP and Port from the 'addr' field
                            ip, port_str = addr.rsplit(':', 1)
                            port = int(port_str)
                        except ValueError:
                            # Skip server if address parsing fails
                            server['ping'] = 'Parse Error'
                            continue

                    if ip and port:
                        # Submit the ping function call to the thread pool
                        future = executor.submit(ping_server, ip, port)
                        future_to_server[future] = server
                    else:
                        server['ping'] = 'Invalid Addr'

                # 2. Collect results as they complete
                for future in concurrent.futures.as_completed(future_to_server):
                    server = future_to_server[future]
                    try:
                        ping_result = future.result()
                        
                        # Update the 'ping' key based on the result
                        if ping_result == -1:
                            server['ping'] = 'Error'
                        elif ping_result == 999:
                            server['ping'] = 'Timeout'
                        else:
                            server['ping'] = str(ping_result)
                            
                    except Exception as exc:
                        print(f'{server.get("addr")} generated an exception: {exc}')
                        server['ping'] = 'Error'

            self.servers = new_servers

            # --- CRITICAL DIAGNOSTIC LOGGING ---
            # Print the ping of the first three servers to confirm update success
            print("\n--- PINGING DIAGNOSTIC (After Pinging) ---")
            for i, server in enumerate(self.servers[:3]):
                print(f"Server {i+1} Ping Value in Memory: {server.get('ping', 'Error')}")
            print("------------------------------------------\n")
            
            if self.servers:
                print(f"Scraper returned {len(self.servers)} servers, pinging complete.")
                
                try:
                    if self.window.winfo_exists():
                        # Step 3: Display results on the main thread
                        self.window.after(0, self.display_servers)
                except tk.TclError:
                    return
            else:
                print("Scraper returned no servers")
                try:
                    if self.window.winfo_exists():
                        self.window.after(0, lambda: self.status_label.config(text="Error: No servers found", fg="#e74c3c"))
                except tk.TclError:
                    return
                        
        except Exception as e:
            print(f"Error in fetch thread: {e}")
            try:
                if self.window.winfo_exists():
                    self.window.after(0, lambda: self.status_label.config(text=f"Error: {str(e)}", fg="#e74c3c"))
            except tk.TclError:
                pass
        finally:
            try:
                if self.window.winfo_exists():
                    self.window.after(0, lambda: self.refresh_button.config(state="normal"))
                    self.window.after(0, lambda: self.filter_button.config(state="normal"))
            except tk.TclError:
                pass

    def display_servers(self):
        """Display servers with improved filtering"""
        # Clear existing entries
        for item in self.server_tree.get_children():
            self.server_tree.delete(item)

        print(f"\n--- FILTER DEBUG: Looking for '{self.mod_filter}' ---")
        mod_strings_to_check = self.mod_name_map.get(self.mod_filter, [])
        print(f"Filter strings: {mod_strings_to_check}")

        if self.mod_filter == 'All Mods':
            filtered_servers = self.servers
        else:
            filtered_servers = []
            for server in self.servers:
                server_mod_raw = server.get('mod', 'n/a')
                server_mod_sanitized = self._sanitize_string(server_mod_raw)
                
                found_match = False
                for mod_string in mod_strings_to_check:
                    sanitized_filter = self._sanitize_string(mod_string)
                    if sanitized_filter and sanitized_filter in server_mod_sanitized:
                        found_match = True
                        break
                
                if found_match:
                    filtered_servers.append(server)

        print(f"Filtered {len(self.servers)} -> {len(filtered_servers)} servers")

        # Populate the tree
        for i, server in enumerate(filtered_servers):
            hostname = server.get('hostname', 'Unknown Server')
            addr = server.get('addr', 'N/A')
            mapname = server.get('mapname', 'N/A')
            clients = str(server.get('clients', 'N/A'))
            mod = server.get('mod', 'N/A')
            gametype = server.get('gametype', 'N/A')
            ping = str(server.get('ping', 'N/A'))
            
            self.server_tree.insert('', 'end', iid=f"server_{i}", 
                                   values=(hostname, addr, mapname, clients, mod, gametype, ping))

        status_text = f"Loaded {len(self.servers)} servers. Displaying {len(filtered_servers)} for '{self.mod_filter}'"
        self.status_label.config(text=status_text, fg=self.text_color)

    def open_filter_popup(self):
        """Opens filter popup"""
        MOD_OPTIONS = ['All Mods'] + sorted([key for key in self.mod_name_map.keys() if key != 'All Mods'])

        if self.filter_popup and self.filter_popup.winfo_exists():
            self.filter_popup.focus_set()
            return

        self.filter_popup = tk.Toplevel(self.window)
        self.filter_popup.title("Filter by Mod")
        self.filter_popup.configure(bg=self.dark_background_color)
        self.filter_popup.transient(self.window)
        self.filter_popup.geometry("300x400")
        
        if self.icon_path_ico:
            self.filter_popup.iconbitmap(self.icon_path_ico)

        tk.Label(self.filter_popup, text="Select Mod to Display:",
                 bg=self.dark_background_color, fg=self.text_color, 
                 font=('Helvetica', 10, 'bold')).pack(pady=10, padx=10)

        self.mod_filter_var = tk.StringVar(self.filter_popup, value=self.mod_filter)

        for mod_name in MOD_OPTIONS:
            rb = tk.Radiobutton(self.filter_popup, text=mod_name, variable=self.mod_filter_var, 
                               value=mod_name, bg=self.dark_background_color, fg=self.text_color, 
                               selectcolor=self.dark_widget_color, relief='flat', 
                               activebackground=self.dark_background_color, 
                               activeforeground=self.text_color)
            rb.pack(anchor='w', padx=20, pady=2)

        button_frame = tk.Frame(self.filter_popup, bg=self.dark_background_color)
        button_frame.pack(pady=15, padx=20)

        apply_button = tk.Button(button_frame, text="Apply Filter", command=self.apply_mod_filter, 
                                bg=self.highlight_color, fg=self.text_color, 
                                activebackground=self.border_color, 
                                relief="raised", font=("Helvetica", 9, "bold"))
        apply_button.pack(side=tk.LEFT, padx=5)

        cancel_button = tk.Button(button_frame, text="Cancel", command=self.filter_popup.destroy, 
                                 bg=self.border_color, fg=self.text_color, 
                                 activebackground=self.highlight_color, 
                                 relief="raised", font=("Helvetica", 9, "bold"))
        cancel_button.pack(side=tk.LEFT, padx=5)
        
        # Center the popup
        self.filter_popup.update_idletasks()
        x = self.window.winfo_x() + self.window.winfo_width() // 2 - self.filter_popup.winfo_width() // 2
        y = self.window.winfo_y() + self.window.winfo_height() // 2 - self.filter_popup.winfo_height() // 2
        self.filter_popup.geometry(f'+{x}+{y}')

    def apply_mod_filter(self):
        """Apply the selected mod filter"""
        self.mod_filter = self.mod_filter_var.get()
        self.filter_popup.destroy()
        self.display_servers()

if __name__ == '__main__':
    root = tk.Tk()
    # Apply global background color before main app takes over
    root.configure(bg="#121212")
    GitHubReleaseManager(root)
    root.mainloop()