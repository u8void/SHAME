SYSTEM: You are an AI PC assistant. The user will ask you to perform tasks. Respond with a single JSON object that describes the action to take.

Available actions:
- open_website(url)
- open_app(name)
- youtube_video(query)
- youtube_channel(name)
- send_email(to, subject, body)          // to can be email or contact name
- open_file(path)                        // absolute or relative path
- search_files(query, folder)            // finds files/folders by name
- run_command(command)                   // executes a shell command
- volume_up, volume_down, volume_mute    // control system volume
- volume_set(percent)                    // set volume 0-100
- brightness_up, brightness_down, brightness_set(percent)
- system_info(what)                      // "cpu", "memory", "disk", "ip", "hostname", "all"
- clipboard_copy(text)
- clipboard_read                         // returns current clipboard text
- chat(response)                         // just reply conversationally

For actions that need parameters, output JSON exactly like:
{"action": "open_website", "url": "https://example.com"}
{"action": "run_command", "command": "ping -c 4 google.com"}
{"action": "chat", "response": "Hello! How can I help?"}

If the user's request is unclear or not an action, use the "chat" action with a helpful message. Output ONLY the JSON, no other text.

# Extended PC Control Training Data for Iris (JSON Actions)

USER: open youtube.com
BOT: {"action": "open_website", "url": "youtube.com"}

USER: go to reddit.com
BOT: {"action": "open_website", "url": "reddit.com"}

USER: browse to github.com
BOT: {"action": "open_website", "url": "github.com"}

USER: navigate to facebook.com
BOT: {"action": "open_website", "url": "facebook.com"}

USER: show me twitter.com
BOT: {"action": "open_website", "url": "twitter.com"}

USER: load https://news.ycombinator.com
BOT: {"action": "open_website", "url": "https://news.ycombinator.com"}

USER: open stackoverflow
BOT: {"action": "open_website", "url": "stackoverflow.com"}

USER: open my gmail
BOT: {"action": "open_website", "url": "gmail.com"}

USER: go to amazon
BOT: {"action": "open_website", "url": "amazon.com"}

USER: open spotify
BOT: {"action": "open_app", "name": "spotify"}

USER: launch notepad
BOT: {"action": "open_app", "name": "notepad"}

USER: start chrome
BOT: {"action": "open_app", "name": "chrome"}

USER: open the calculator
BOT: {"action": "open_app", "name": "calculator"}

USER: run vscode
BOT: {"action": "open_app", "name": "vscode"}

USER: open terminal
BOT: {"action": "open_app", "name": "terminal"}

USER: launch firefox
BOT: {"action": "open_app", "name": "firefox"}

USER: start word
BOT: {"action": "open_app", "name": "word"}

USER: open excel
BOT: {"action": "open_app", "name": "excel"}

USER: open paint
BOT: {"action": "open_app", "name": "paint"}

USER: play Bohemian Rhapsody on youtube
BOT: {"action": "youtube_video", "query": "Bohemian Rhapsody"}

USER: play no one noticed on spotify
BOT: {"action": "spotify_song", "query": "no one noticed"}

USER: open the song 'blinding lights' on spotify
BOT: {"action": "spotify_song", "query": "blinding lights"}

USER: spotify: starboy
BOT: {"action": "spotify_song", "query": "starboy"}

USER: listen to linkin park on spotify
BOT: {"action": "spotify_song", "query": "linkin park"}

USER: search for jazz on spotify
BOT: {"action": "spotify_song", "query": "jazz"}

USER: watch cat videos on youtube
BOT: {"action": "youtube_video", "query": "cat videos"}

USER: find how to cook pasta on youtube
BOT: {"action": "youtube_video", "query": "how to cook pasta"}

USER: open a song on youtube: Never Gonna Give You Up
BOT: {"action": "youtube_video", "query": "Never Gonna Give You Up"}

USER: search for lo-fi beats on youtube
BOT: {"action": "youtube_video", "query": "lo-fi beats"}

USER: play someone like you on yt
BOT: {"action": "youtube_video", "query": "someone like you"}

USER: youtube video: funny dogs
BOT: {"action": "youtube_video", "query": "funny dogs"}

USER: open MrBeast channel on youtube
BOT: {"action": "youtube_channel", "name": "MrBeast"}

USER: find NASA channel on youtube
BOT: {"action": "youtube_channel", "name": "NASA"}

USER: show me the Veritasium channel
BOT: {"action": "youtube_channel", "name": "Veritasium"}

USER: go to Kurzgesagt channel on youtube
BOT: {"action": "youtube_channel", "name": "Kurzgesagt"}

USER: open john oliver channel
BOT: {"action": "youtube_channel", "name": "John Oliver"}

USER: send an email to mom about dinner
BOT: {"action": "send_email", "to": "mom", "subject": "dinner", "body": ""}

USER: email dad subject birthday body Don't forget the cake
BOT: {"action": "send_email", "to": "dad", "subject": "birthday", "body": "Don't forget the cake"}

USER: compose an email to boss@company.com subject meeting body I'll be 10 minutes late
BOT: {"action": "send_email", "to": "boss@company.com", "subject": "meeting", "body": "I'll be 10 minutes late"}

USER: write an email to work about the project update
BOT: {"action": "send_email", "to": "work", "subject": "project update", "body": ""}

USER: send a mail to john@example.com saying hello
BOT: {"action": "send_email", "to": "john@example.com", "subject": "hello", "body": ""}

USER: email mom subject I'm on my way
BOT: {"action": "send_email", "to": "mom", "subject": "I'm on my way", "body": ""}

USER: open the budget folder
BOT: {"action": "open_file", "path": "budget"}

USER: open my documents
BOT: {"action": "open_file", "path": "Documents"}

USER: open /Users/alice/Desktop/report.pdf
BOT: {"action": "open_file", "path": "/Users/alice/Desktop/report.pdf"}

USER: open C:\Users\Bob\Downloads\presentation.pptx
BOT: {"action": "open_file", "path": "C:\\Users\\Bob\\Downloads\\presentation.pptx"}

USER: open the file notes.txt
BOT: {"action": "open_file", "path": "notes.txt"}

USER: open ~/.bashrc
BOT: {"action": "open_file", "path": "~/.bashrc"}

USER: open the photos folder
BOT: {"action": "open_file", "path": "photos"}

USER: search for .txt files in Downloads
BOT: {"action": "search_files", "query": ".txt", "folder": "Downloads"}

USER: find all PDFs in my Documents
BOT: {"action": "search_files", "query": ".pdf", "folder": "Documents"}

USER: look for budget spreadsheet on desktop
BOT: {"action": "search_files", "query": "budget", "folder": "Desktop"}

USER: find files named *.py in current directory
BOT: {"action": "search_files", "query": "*.py", "folder": "."}

USER: search for family photos in Pictures
BOT: {"action": "search_files", "query": "family", "folder": "Pictures"}

USER: list all jpg images in home
BOT: {"action": "search_files", "query": ".jpg", "folder": "~"}

USER: find application forms in /Users/jane/Desktop
BOT: {"action": "search_files", "query": "application", "folder": "/Users/jane/Desktop"}

USER: run ping google.com
BOT: {"action": "run_command", "command": "ping google.com"}

USER: run ipconfig /all
BOT: {"action": "run_command", "command": "ipconfig /all"}

USER: execute ls -la
BOT: {"action": "run_command", "command": "ls -la"}

USER: run cal 2026
BOT: {"action": "run_command", "command": "cal 2026"}

USER: run ip addr show
BOT: {"action": "run_command", "command": "ip addr show"}

USER: execute echo Hello World
BOT: {"action": "run_command", "command": "echo Hello World"}

USER: run command: whoami
BOT: {"action": "run_command", "command": "whoami"}

USER: volume up
BOT: {"action": "volume_up"}

USER: turn the volume down
BOT: {"action": "volume_down"}

USER: mute speakers
BOT: {"action": "volume_mute"}

USER: mute volume
BOT: {"action": "volume_mute"}

USER: unmute
BOT: {"action": "volume_up"}

USER: set volume to 70 percent
BOT: {"action": "volume_set", "percent": 70}

USER: volume to 30%
BOT: {"action": "volume_set", "percent": 30}

USER: make it louder
BOT: {"action": "volume_up"}

USER: decrease the sound
BOT: {"action": "volume_down"}

USER: set volume to max
BOT: {"action": "volume_set", "percent": 100}

USER: volume at 0%
BOT: {"action": "volume_set", "percent": 0}

USER: brightness up
BOT: {"action": "brightness_up"}

USER: lower the brightness
BOT: {"action": "brightness_down"}

USER: set brightness to 40%
BOT: {"action": "brightness_set", "percent": 40}

USER: dim the screen
BOT: {"action": "brightness_down"}

USER: brightness 80%
BOT: {"action": "brightness_set", "percent": 80}

USER: max brightness
BOT: {"action": "brightness_set", "percent": 100}

USER: minimum brightness
BOT: {"action": "brightness_set", "percent": 0}

USER: what's my IP address?
BOT: {"action": "system_info", "what": "ip"}

USER: how much RAM do I have?
BOT: {"action": "system_info", "what": "memory"}

USER: show me the hostname
BOT: {"action": "system_info", "what": "hostname"}

USER: system info
BOT: {"action": "system_info", "what": "all"}

USER: what's my CPU?
BOT: {"action": "system_info", "what": "cpu"}

USER: disk space left
BOT: {"action": "system_info", "what": "disk"}

USER: tell me about my memory
BOT: {"action": "system_info", "what": "memory"}

USER: copy 'hello world' to clipboard
BOT: {"action": "clipboard_copy", "text": "hello world"}

USER: copy the text: Meeting at 3 PM
BOT: {"action": "clipboard_copy", "text": "Meeting at 3 PM"}

USER: copy this link: https://example.com
BOT: {"action": "clipboard_copy", "text": "https://example.com"}

USER: copy "Remember to buy milk"
BOT: {"action": "clipboard_copy", "text": "Remember to buy milk"}

USER: read clipboard
BOT: {"action": "clipboard_read"}

USER: what's on my clipboard?
BOT: {"action": "clipboard_read"}

USER: show clipboard
BOT: {"action": "clipboard_read"}

USER: tell me a joke
BOT: {"action": "chat", "response": "Why don't scientists trust atoms? Because they make up everything!"}

USER: how are you?
BOT: {"action": "chat", "response": "I'm functioning perfectly. How can I assist you?"}

USER: thanks
BOT: {"action": "chat", "response": "You're welcome!"}

USER: what's the weather like?
BOT: {"action": "chat", "response": "I can't fetch live weather, but I can open a weather site for you. Would you like that?"}

USER: open weather.com
BOT: {"action": "open_website", "url": "weather.com"}

USER: play some music on youtube
BOT: {"action": "chat", "response": "What song or genre would you like me to play on YouTube?"}

USER: search for funny videos on youtube
BOT: {"action": "chat", "response": "Any specific kind of funny videos? I can search for 'funny cats' or 'stand‑up comedy' for example."}

USER: shut down the computer in 10 minutes
BOT: {"action": "run_command", "command": "shutdown -h +10"}

USER: restart the computer
BOT: {"action": "chat", "response": "I can run a restart command, but please confirm you want that. If yes, say `run shutdown -r now`."}

USER: run shutdown -r now
BOT: {"action": "run_command", "command": "shutdown -r now"}

USER: copy system info to clipboard
BOT: {"action": "chat", "response": "I can't directly pipe results. First use `system info`, then `copy <result>` manually."}

USER: open the app "Photos"
BOT: {"action": "open_app", "name": "photos"}

USER: launch the settings app
BOT: {"action": "open_app", "name": "settings"}

USER: start system preferences
BOT: {"action": "open_file", "path": "/System/Applications/System Preferences.app"}

USER: open control panel
BOT: {"action": "run_command", "command": "control"}

USER: open the downloads folder
BOT: {"action": "open_file", "path": "Downloads"}

USER: play despacito on youtube
BOT: {"action": "youtube_video", "query": "despacito"}

USER: find the channel "Kurzgesagt" on youtube
BOT: {"action": "youtube_channel", "name": "Kurzgesagt"}

USER: open the website en.wikipedia.org
BOT: {"action": "open_website", "url": "en.wikipedia.org"}

USER: search for nearest coffee shop
BOT: {"action": "open_website", "url": "https://www.google.com/search?q=nearest+coffee+shop"}

USER: look up "how to tie a tie" on youtube
BOT: {"action": "youtube_video", "query": "how to tie a tie"}

USER: compose email to support@company.com subject Issue with order body My order #12345 hasn't arrived.
BOT: {"action": "send_email", "to": "support@company.com", "subject": "Issue with order", "body": "My order #12345 hasn't arrived."}

USER: email mom subject visit body I'll visit next Sunday.
BOT: {"action": "send_email", "to": "mom", "subject": "visit", "body": "I'll visit next Sunday."}

USER: open the hidden file .env
BOT: {"action": "open_file", "path": ".env"}

USER: open /etc/hosts
BOT: {"action": "open_file", "path": "/etc/hosts"}

USER: find all node_modules folders in current project
BOT: {"action": "search_files", "query": "node_modules", "folder": "."}

USER: search for presentation files with prefix "Q4"
BOT: {"action": "search_files", "query": "Q4*", "folder": "Documents"}

USER: run command: ps aux
BOT: {"action": "run_command", "command": "ps aux"}

USER: run netstat -an
BOT: {"action": "run_command", "command": "netstat -an"}

USER: volume a bit higher
BOT: {"action": "volume_up"}

USER: slightly lower volume
BOT: {"action": "volume_down"}

USER: brightness down a notch
BOT: {"action": "brightness_down"}

USER: set volume to 45%
BOT: {"action": "volume_set", "percent": 45}

USER: brightness 25%
BOT: {"action": "brightness_set", "percent": 25}

USER: get computer name
BOT: {"action": "system_info", "what": "hostname"}

USER: show processor details
BOT: {"action": "system_info", "what": "cpu"}

USER: clipboard copy the path /usr/local/bin
BOT: {"action": "clipboard_copy", "text": "/usr/local/bin"}

USER: copy this phrase to clipboard: "Meeting at noon"
BOT: {"action": "clipboard_copy", "text": "Meeting at noon"}

USER: what's currently copied?
BOT: {"action": "clipboard_read"}

USER: open a new tab in browser
BOT: {"action": "chat", "response": "I can open a website, but I can't directly create a new tab. Would you like to open a blank page?"}

USER: close current window
BOT: {"action": "chat", "response": "I'm not able to close windows directly. I can only perform the actions I know."}

USER: take a screenshot
BOT: {"action": "chat", "response": "Screenshot capability isn't built in yet. Would you like me to run a screenshot command?"}

USER: run screenshot command: screencapture -x ~/Desktop/screenshot.png
BOT: {"action": "run_command", "command": "screencapture -x ~/Desktop/screenshot.png"}

USER: open the calculator and notepad
BOT: {"action": "chat", "response": "I can only do one action at a time. Which would you like first?"}

USER: open two apps at once
BOT: {"action": "chat", "response": "I can handle them one after another. Tell me the first one."}

USER: show desktop
BOT: {"action": "run_command", "command": "open /System/Applications/Mission Control.app"}

USER: lock the computer
BOT: {"action": "run_command", "command": "pmset displaysleepnow"}

USER: sleep the display
BOT: {"action": "run_command", "command": "pmset displaysleepnow"}

USER: find all images on desktop
BOT: {"action": "search_files", "query": ".png .jpg .jpeg .gif", "folder": "Desktop"}

USER: play the latest from Coldplay on YouTube
BOT: {"action": "youtube_video", "query": "Coldplay official"}

USER: show me the NASA live stream on youtube
BOT: {"action": "youtube_video", "query": "NASA live"}

USER: open notepad and then write something
BOT: {"action": "chat", "response": "I'll open notepad first. Just say 'open notepad' to start."}

USER: make the computer louder
BOT: {"action": "volume_up"}

USER: silence the computer
BOT: {"action": "volume_mute"}

USER: bring back the sound
BOT: {"action": "volume_up"}

USER: turn off the screen
BOT: {"action": "chat", "response": "I can't power off the display directly, but I can dim it to 0%."}

USER: dim screen to minimum
BOT: {"action": "brightness_set", "percent": 0}

USER: brighten the screen
BOT: {"action": "brightness_up"}

USER: make screen very bright
BOT: {"action": "brightness_set", "percent": 100"}

USER: show my ip address
BOT: {"action": "system_info", "what": "ip"}

USER: how much disk space is free?
BOT: {"action": "system_info", "what": "disk"}

USER: what is my ram usage?
BOT: {"action": "system_info", "what": "memory"}

USER: email boss subject status update body Everything is on track.
BOT: {"action": "send_email", "to": "boss", "subject": "status update", "body": "Everything is on track."}

USER: send mail to colleague@work.com subject handover
BOT: {"action": "send_email", "to": "colleague@work.com", "subject": "handover", "body": ""}

USER: play shape of you on yt
BOT: {"action": "youtube_video", "query": "shape of you"}

USER: open youtube channel kurzgesagt
BOT: {"action": "youtube_channel", "name": "kurzgesagt"}

USER: go to youtube.com
BOT: {"action": "open_website", "url": "youtube.com"}

USER: open github.com/new
BOT: {"action": "open_website", "url": "github.com/new"}

USER: launch textedit on mac
BOT: {"action": "open_app", "name": "textedit"}

USER: copy the current date to clipboard
BOT: {"action": "chat", "response": "I can't create dates dynamically, but you can give me a text to copy."}

USER: share clipboard content
BOT: {"action": "chat", "response": "Use 'read clipboard' to see what's inside."}

USER: volume at middle
BOT: {"action": "volume_set", "percent": 50}

USER: brightness 50
BOT: {"action": "brightness_set", "percent": 50}

USER: open the home folder
BOT: {"action": "open_file", "path": "~"}

USER: show me the desktop
BOT: {"action": "open_file", "path": "Desktop"}

USER: search for budget in all documents
BOT: {"action": "search_files", "query": "budget", "folder": "Documents"}

USER: run top command
BOT: {"action": "run_command", "command": "top -l 1"}

USER: run ifconfig
BOT: {"action": "run_command", "command": "ifconfig"}

USER: run dir on windows
BOT: {"action": "run_command", "command": "dir"}

USER: run ls on mac
BOT: {"action": "run_command", "command": "ls"}

USER: execute python script.py
BOT: {"action": "run_command", "command": "python script.py"}

USER: open terminal and run ping localhost
BOT: {"action": "chat", "response": "I'll open terminal first. Then tell me to run the ping command."}

USER: open google.com then search for cats
BOT: {"action": "chat", "response": "Let's do that in two steps. Say 'open google.com' first."}

USER: youtube search for "learn french"
BOT: {"action": "youtube_video", "query": "learn french"}

USER: find channel "TED" on youtube
BOT: {"action": "youtube_channel", "name": "TED"}

USER: send an email to myself reminder subject dentist body Today 4pm
BOT: {"action": "send_email", "to": "myself", "subject": "dentist", "body": "Today 4pm"}

USER: compose email to friend@mail.com subject party body You're invited!
BOT: {"action": "send_email", "to": "friend@mail.com", "subject": "party", "body": "You're invited!"}

USER: turn up the system sound
BOT: {"action": "volume_up"}

USER: reduce the brightness of the screen
BOT: {"action": "brightness_down"}

USER: set screen brightness to 75
BOT: {"action": "brightness_set", "percent": 75}

USER: system specs
BOT: {"action": "system_info", "what": "all"}

USER: clipboard copy the command output
BOT: {"action": "chat", "response": "I can't copy previous outputs, but I can show you the clipboard."}

USER: open the file resume.docx
BOT: {"action": "open_file", "path": "resume.docx"}

USER: search for *.iso in Downloads
BOT: {"action": "search_files", "query": "*.iso", "folder": "Downloads"}

USER: mute microphone
BOT: {"action": "chat", "response": "I don't have microphone control yet."}

USER: pause music
BOT: {"action": "chat", "response": "I can't control media playback directly, but I can open your music app."}

USER: next track
BOT: {"action": "chat", "response": "I can't skip tracks. Would you like to open Spotify?"}

USER: play the weeknd on youtube
BOT: {"action": "youtube_video", "query": "the weeknd"}

USER: open the Facebook app
BOT: {"action": "open_app", "name": "facebook"}

USER: launch whatsapp
BOT: {"action": "open_app", "name": "whatsapp"}

USER: start telegram
BOT: {"action": "open_app", "name": "telegram"}

USER: open notepad++ on windows
BOT: {"action": "open_app", "name": "notepad++"}

USER: run npm install
BOT: {"action": "run_command", "command": "npm install"}

USER: run git status
BOT: {"action": "run_command", "command": "git status"}

USER: run docker ps
BOT: {"action": "run_command", "command": "docker ps"}

USER: find the browser executable and open it
BOT: {"action": "chat", "response": "Which browser? Chrome, Firefox, or Edge?"}

USER: open chrome
BOT: {"action": "open_app", "name": "chrome"}

USER: what time is it?
BOT: {"action": "run_command", "command": "date '+%H:%M:%S'"}

USER: what's today's date?
BOT: {"action": "run_command", "command": "date '+%Y-%m-%d'"}

USER: show me the ls command output
BOT: {"action": "run_command", "command": "ls"}

USER: list all running processes
BOT: {"action": "run_command", "command": "ps aux"}

USER: find large files over 1GB
BOT: {"action": "run_command", "command": "find / -type f -size +1G 2>/dev/null"}

USER: volume 20% and then open browser
BOT: {"action": "chat", "response": "I can do volume 20% first. Let's start there."}

USER: open vscode and the project folder
BOT: {"action": "chat", "response": "I can open VS Code first. Then you can open the folder."}

USER: play the song "blinding lights"
BOT: {"action": "youtube_video", "query": "blinding lights"}

USER: show me cute puppies on youtube
BOT: {"action": "youtube_video", "query": "cute puppies"}

USER: open the microsoft store app
BOT: {"action": "open_app", "name": "microsoft store"}

USER: open settings app in windows
BOT: {"action": "run_command", "command": "start ms-settings:"}

USER: open system preferences on mac
BOT: {"action": "open_file", "path": "/System/Applications/System Preferences.app"}

USER: copy the wifi password to clipboard
BOT: {"action": "chat", "response": "I'm not able to extract WiFi passwords. I can run a command if you know one."}

USER: run security find-generic-password -wa "MyWiFi"
BOT: {"action": "run_command", "command": "security find-generic-password -wa \"MyWiFi\""}

USER: empty the recycle bin
BOT: {"action": "chat", "response": "I can't modify files for safety reasons. You can use File Explorer."}

USER: eject the usb drive
BOT: {"action": "run_command", "command": "diskutil eject /Volumes/USB"}

USER: open my pictures
BOT: {"action": "open_file", "path": "Pictures"}

USER: browse to /usr/bin
BOT: {"action": "open_file", "path": "/usr/bin"}

USER: search for python scripts in ./src
BOT: {"action": "search_files", "query": "*.py", "folder": "./src"}

USER: find readme files in current project
BOT: {"action": "search_files", "query": "README*", "folder": "."}

USER: make screen darker
BOT: {"action": "brightness_down"}

USER: system sound up
BOT: {"action": "volume_up"}

USER: completely mute
BOT: {"action": "volume_mute"}

USER: copy "Good morning" to clipboard
BOT: {"action": "clipboard_copy", "text": "Good morning"}

USER: clipboard: "https://iris.ai"
BOT: {"action": "clipboard_copy", "text": "https://iris.ai"}

USER: what's the clipboard content?
BOT: {"action": "clipboard_read"}

USER: check clipboard
BOT: {"action": "clipboard_read"}

USER: tell me a fun fact
BOT: {"action": "chat", "response": "Honey never spoils. Archaeologists have found pots of honey in ancient Egyptian tombs that are over 3,000 years old and still perfectly edible."}
# Troubleshooting & Terminal
USER: my internet is slow, check it
BOT: {"action": "run_command", "command": "ping -c 4 google.com"}

USER: check why my mac is loud
BOT: {"action": "run_command", "command": "top -o cpu -n 10"}

USER: open terminal and run htop
BOT: {"action": "open_terminal", "command": "htop"}

USER: start a new shell
BOT: {"action": "open_terminal"}

USER: what's taking up my disk space?
BOT: {"action": "run_command", "command": "du -sh ~/Documents/* | sort -rh | head -n 10"}

USER: fix my permissions on the desktop
BOT: {"action": "run_command", "command": "chmod -R 755 ~/Desktop"}

USER: I can't connect to wifi
BOT: {"action": "run_command", "command": "networksetup -listallhardwareports"}

USER: clear the system logs
BOT: {"action": "chat", "response": "Clearing system logs usually requires sudo and can be risky. Are you sure? If so, tell me to `run sudo log erase`."}

USER: run sudo log erase
BOT: {"action": "run_command", "command": "sudo log erase"}

USER: show me all running python processes
BOT: {"action": "run_command", "command": "ps aux | grep python"}

USER: find where java is installed
BOT: {"action": "run_command", "command": "which java"}

USER: open the terminal and ping my router
BOT: {"action": "open_terminal", "command": "ping 192.168.1.1"}

USER: check for system updates
BOT: {"action": "run_command", "command": "softwareupdate -l"}

USER: install all updates
BOT: {"action": "run_command", "command": "softwareupdate -ia"}
