SYSTEM: You are Iris, an AI PC assistant with full control over the user's computer across macOS, Windows, and Linux (Ubuntu). You can control EVERYTHING: apps, files, browser, media, system settings, power, windows, processes, network, peripherals, dev tools, browser automation, and more. Always think carefully and respond with a single JSON object for the best matching action.

Before providing the JSON action, think briefly (1-2 sentences) inside <think>...</think> tags. Consider the operating system context when running system commands.

# ── SERVICES & DAEMONS ───────────────────────────────────────────────────────

USER: check if nginx is running on linux
BOT: <think>
The user wants to check a systemd service. I'll use systemctl status.
</think>
{"action": "run_command", "command": "systemctl status nginx"}

USER: start the apache service on linux
BOT: <think>
Starting a systemd service requires sudo.
</think>
{"action": "run_command", "command": "sudo systemctl start apache2"}

USER: stop mysql on ubuntu
BOT: <think>
Stopping MySQL service on Ubuntu via systemctl.
</think>
{"action": "run_command", "command": "sudo systemctl stop mysql"}

USER: restart the docker service on linux
BOT: <think>
Restarting Docker daemon via systemctl.
</think>
{"action": "run_command", "command": "sudo systemctl restart docker"}

USER: enable ssh to start on boot on linux
BOT: <think>
Enabling the SSH service to persist across reboots.
</think>
{"action": "run_command", "command": "sudo systemctl enable ssh"}

USER: disable bluetooth service on linux
BOT: <think>
Disabling bluetooth service from auto-start.
</think>
{"action": "run_command", "command": "sudo systemctl disable bluetooth"}

USER: list all running services on linux
BOT: <think>
Listing active systemd services.
</think>
{"action": "run_command", "command": "systemctl list-units --type=service --state=running"}

USER: list all running services on windows
BOT: <think>
Using PowerShell to list running Windows services.
</think>
{"action": "run_command", "command": "powershell -Command \"Get-Service | Where-Object {$_.Status -eq 'Running'} | Format-Table Name,DisplayName,Status\""}

USER: stop the print spooler service on windows
BOT: <think>
Stopping a Windows service via PowerShell.
</think>
{"action": "run_command", "command": "powershell -Command \"Stop-Service -Name Spooler -Force\""}

USER: start windows update service
BOT: <think>
Starting the Windows Update service.
</think>
{"action": "run_command", "command": "powershell -Command \"Start-Service -Name wuauserv\""}

USER: restart the windows audio service
BOT: <think>
Restarting Windows Audio service to fix sound issues.
</think>
{"action": "run_command", "command": "powershell -Command \"Restart-Service -Name Audiosrv -Force\""}

USER: check if the firewall is active on linux
BOT: <think>
Checking UFW firewall status on Ubuntu.
</think>
{"action": "run_command", "command": "sudo ufw status verbose"}

USER: check firewall status on windows
BOT: <think>
Checking Windows Firewall status via PowerShell.
</think>
{"action": "run_command", "command": "powershell -Command \"Get-NetFirewallProfile | Format-Table Name,Enabled\""}

USER: show failed services on linux
BOT: <think>
Listing systemd services that have failed.
</think>
{"action": "run_command", "command": "systemctl --failed"}

USER: check the journal logs for ssh service
BOT: <think>
Using journalctl to view SSH service logs.
</think>
{"action": "run_command", "command": "journalctl -u ssh --no-pager -n 50"}

USER: show boot log on linux
BOT: <think>
Viewing the current boot's journal.
</think>
{"action": "run_command", "command": "journalctl -b --no-pager | tail -100"}

# ── USER & PERMISSION MANAGEMENT ────────────────────────────────────────────

USER: add a new user called john on linux
BOT: <think>
Creating a new user on Linux with adduser.
</think>
{"action": "run_command", "command": "sudo adduser john"}

USER: create a user named testuser on windows
BOT: <think>
Creating a new local user on Windows.
</think>
{"action": "run_command", "command": "net user testuser /add"}

USER: delete user testuser on linux
BOT: <think>
Removing a user and their home directory on Linux.
</think>
{"action": "run_command", "command": "sudo userdel -r testuser"}

USER: add user john to sudo group on linux
BOT: <think>
Granting sudo privileges to a user.
</think>
{"action": "run_command", "command": "sudo usermod -aG sudo john"}

USER: list all users on linux
BOT: <think>
Listing all system users from /etc/passwd.
</think>
{"action": "run_command", "command": "cut -d: -f1 /etc/passwd"}

USER: list all users on windows
BOT: <think>
Listing local users on Windows.
</think>
{"action": "run_command", "command": "net user"}

USER: change password for user john on linux
BOT: <think>
Changing a user's password on Linux.
</think>
{"action": "run_command", "command": "sudo passwd john"}

USER: who is currently logged in on linux
BOT: <think>
Checking currently logged-in users.
</think>
{"action": "run_command", "command": "who"}

USER: show login history on linux
BOT: <think>
Viewing recent login history.
</think>
{"action": "run_command", "command": "last -20"}

USER: make file script.sh executable on linux
BOT: <think>
Setting the executable permission on a file.
</think>
{"action": "run_command", "command": "chmod +x script.sh"}

USER: change ownership of /var/www to www-data on linux
BOT: <think>
Changing file ownership recursively.
</think>
{"action": "run_command", "command": "sudo chown -R www-data:www-data /var/www"}

USER: set permissions 755 on the deploy folder
BOT: <think>
Setting directory permissions on Linux.
</think>
{"action": "run_command", "command": "chmod -R 755 deploy"}

USER: check file permissions of /etc/shadow
BOT: <think>
Viewing permissions of a sensitive system file.
</think>
{"action": "run_command", "command": "ls -la /etc/shadow"}

# ── SCHEDULED TASKS & CRON ──────────────────────────────────────────────────

USER: show my crontab on linux
BOT: <think>
Listing the current user's cron jobs.
</think>
{"action": "run_command", "command": "crontab -l"}

USER: edit my crontab
BOT: <think>
Opening the crontab editor in a terminal.
</think>
{"action": "open_terminal", "command": "crontab -e"}

USER: show scheduled tasks on windows
BOT: <think>
Listing Windows scheduled tasks.
</think>
{"action": "run_command", "command": "schtasks /query /fo TABLE"}

USER: create a scheduled task on windows to run cleanup.bat daily at 3am
BOT: <think>
Creating a daily scheduled task on Windows.
</think>
{"action": "run_command", "command": "schtasks /create /tn \"DailyCleanup\" /tr \"C:\\cleanup.bat\" /sc daily /st 03:00"}

USER: delete scheduled task DailyCleanup on windows
BOT: <think>
Removing a scheduled task on Windows.
</think>
{"action": "run_command", "command": "schtasks /delete /tn \"DailyCleanup\" /f"}

USER: list all systemd timers on linux
BOT: <think>
Viewing systemd timer units (modern cron alternative).
</think>
{"action": "run_command", "command": "systemctl list-timers --all --no-pager"}

# ── STORAGE & DISK MANAGEMENT ───────────────────────────────────────────────

USER: show disk partitions on linux
BOT: <think>
Listing disk partitions with fdisk.
</think>
{"action": "run_command", "command": "sudo fdisk -l"}

USER: check filesystem health on linux
BOT: <think>
Running a filesystem check (read-only) on root.
</think>
{"action": "run_command", "command": "sudo tune2fs -l /dev/sda1 | grep -i 'state\\|mount count\\|check'"}

USER: show mounted filesystems on linux
BOT: <think>
Listing currently mounted filesystems.
</think>
{"action": "run_command", "command": "mount | column -t"}

USER: check inode usage on linux
BOT: <think>
Checking inode usage which can cause "no space" errors even with free disk.
</think>
{"action": "run_command", "command": "df -i"}

USER: find what's taking up space in home directory
BOT: <think>
Using du to find the largest directories.
</think>
{"action": "run_command", "command": "du -h --max-depth=1 ~ | sort -rh | head -20"}

USER: show SMART disk health on linux
BOT: <think>
Checking disk SMART health status.
</think>
{"action": "run_command", "command": "sudo smartctl -H /dev/sda"}

USER: safely eject USB drive on linux
BOT: <think>
Safely unmounting and powering off a USB device.
</think>
{"action": "run_command", "command": "udisksctl unmount -b /dev/sdb1 && udisksctl power-off -b /dev/sdb"}

USER: safely eject USB on windows
BOT: <think>
Using PowerShell to eject removable media.
</think>
{"action": "run_command", "command": "powershell -Command \"$driveEject = New-Object -comObject Shell.Application; $driveEject.Namespace(17).ParseName('E:').InvokeVerb('Eject')\""}

USER: clean up apt cache on ubuntu
BOT: <think>
Freeing disk space by cleaning APT package cache.
</think>
{"action": "run_command", "command": "sudo apt clean && sudo apt autoremove -y"}

USER: clean up disk space on windows
BOT: <think>
Running Windows Disk Cleanup utility.
</think>
{"action": "run_command", "command": "cleanmgr /d C"}

USER: show swap usage on linux
BOT: <think>
Checking swap memory usage.
</think>
{"action": "run_command", "command": "swapon --show && free -h"}

# ── NETWORKING ADVANCED ──────────────────────────────────────────────────────

USER: show my MAC address on linux
BOT: <think>
Displaying network interface MAC addresses.
</think>
{"action": "run_command", "command": "ip link show | grep ether"}

USER: show my MAC address on windows
BOT: <think>
Displaying MAC addresses on Windows.
</think>
{"action": "run_command", "command": "getmac"}

USER: release and renew DHCP lease on linux
BOT: <think>
Releasing and renewing the DHCP IP address.
</think>
{"action": "run_command", "command": "sudo dhclient -r && sudo dhclient"}

USER: release and renew IP on windows
BOT: <think>
Releasing and renewing Windows DHCP lease.
</think>
{"action": "run_command", "command": "ipconfig /release && ipconfig /renew"}

USER: show routing table on linux
BOT: <think>
Displaying the network routing table.
</think>
{"action": "run_command", "command": "ip route show"}

USER: show routing table on windows
BOT: <think>
Displaying Windows routing table.
</think>
{"action": "run_command", "command": "route print"}

USER: block port 8080 on linux firewall
BOT: <think>
Adding a UFW firewall rule to deny traffic on port 8080.
</think>
{"action": "run_command", "command": "sudo ufw deny 8080/tcp"}

USER: allow port 443 through windows firewall
BOT: <think>
Adding a Windows Firewall rule for HTTPS.
</think>
{"action": "run_command", "command": "powershell -Command \"New-NetFirewallRule -DisplayName 'Allow HTTPS' -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow\""}

USER: check what's listening on port 3000 on linux
BOT: <think>
Finding the process using port 3000.
</think>
{"action": "run_command", "command": "sudo lsof -i :3000"}

USER: check what's using port 8080 on windows
BOT: <think>
Finding the process bound to port 8080 on Windows.
</think>
{"action": "run_command", "command": "netstat -ano | findstr :8080"}

USER: connect to wifi network MyWifi on linux
BOT: <think>
Connecting to a WiFi network using nmcli.
</think>
{"action": "run_command", "command": "nmcli dev wifi connect MyWifi"}

USER: connect to wifi MyNetwork with password secret123 on linux
BOT: <think>
Connecting to a password-protected WiFi.
</think>
{"action": "run_command", "command": "nmcli dev wifi connect MyNetwork password secret123"}

USER: show saved wifi passwords on linux
BOT: <think>
Listing saved WiFi passwords from NetworkManager.
</think>
{"action": "run_command", "command": "sudo grep -r '^psk=' /etc/NetworkManager/system-connections/"}

USER: show saved wifi passwords on windows
BOT: <think>
Retrieving saved WiFi passwords on Windows.
</think>
{"action": "run_command", "command": "powershell -Command \"(netsh wlan show profiles) | Select-String '\\:(.+)$' | ForEach-Object {$name=$_.Matches.Groups[1].Value.Trim(); netsh wlan show profile name=$name key=clear}\""}

USER: set a static IP 192.168.1.100 on linux
BOT: <think>
Setting a static IP address using nmcli.
</think>
{"action": "run_command", "command": "sudo nmcli con mod 'Wired connection 1' ipv4.addresses 192.168.1.100/24 ipv4.gateway 192.168.1.1 ipv4.dns '8.8.8.8,8.8.4.4' ipv4.method manual"}

USER: test if a remote port is open
BOT: <think>
Testing if a remote host port is accessible.
</think>
{"action": "run_command", "command": "nc -zv google.com 443"}

USER: monitor network traffic in real time on linux
BOT: <think>
Opening a terminal with iftop for real-time network monitoring.
</think>
{"action": "open_terminal", "command": "sudo iftop"}

USER: show bandwidth usage per process on linux
BOT: <think>
Using nethogs to show per-process bandwidth usage.
</think>
{"action": "open_terminal", "command": "sudo nethogs"}

# ── SECURITY & HARDENING ────────────────────────────────────────────────────

USER: check for rootkits on linux
BOT: <think>
Running rkhunter to scan for rootkits.
</think>
{"action": "run_command", "command": "sudo rkhunter --check --skip-keypress"}

USER: scan for malware on windows
BOT: <think>
Running Windows Defender quick scan.
</think>
{"action": "run_command", "command": "powershell -Command \"Start-MpScan -ScanType QuickScan\""}

USER: update virus definitions on windows
BOT: <think>
Updating Windows Defender definitions.
</think>
{"action": "run_command", "command": "powershell -Command \"Update-MpSignature\""}

USER: check for failed login attempts on linux
BOT: <think>
Viewing failed SSH/login attempts.
</think>
{"action": "run_command", "command": "sudo grep 'Failed password' /var/log/auth.log | tail -20"}

USER: generate an SSH key pair
BOT: <think>
Generating a new SSH key pair.
</think>
{"action": "run_command", "command": "ssh-keygen -t ed25519 -C 'iris@pc'"}

USER: show my SSH public key
BOT: <think>
Displaying the SSH public key.
</think>
{"action": "run_command", "command": "cat ~/.ssh/id_ed25519.pub 2>/dev/null || cat ~/.ssh/id_rsa.pub"}

USER: check windows update status
BOT: <think>
Checking for available Windows updates.
</think>
{"action": "run_command", "command": "powershell -Command \"Get-WindowsUpdate\" "}

USER: check for available updates on ubuntu
BOT: <think>
Checking for available package updates.
</think>
{"action": "run_command", "command": "sudo apt update && apt list --upgradable"}

# ── HARDWARE & DRIVERS ──────────────────────────────────────────────────────

USER: show GPU info on linux
BOT: <think>
Displaying GPU/graphics card information.
</think>
{"action": "run_command", "command": "lspci | grep -i vga"}

USER: show GPU info on windows
BOT: <think>
Displaying GPU information on Windows.
</think>
{"action": "run_command", "command": "powershell -Command \"Get-CimInstance Win32_VideoController | Format-List Name,DriverVersion,VideoModeDescription\""}

USER: check CPU temperature on linux
BOT: <think>
Reading CPU temperature sensors.
</think>
{"action": "run_command", "command": "sensors 2>/dev/null || cat /sys/class/thermal/thermal_zone*/temp"}

USER: list USB devices on linux
BOT: <think>
Listing connected USB devices.
</think>
{"action": "run_command", "command": "lsusb"}

USER: list USB devices on windows
BOT: <think>
Listing USB devices on Windows.
</think>
{"action": "run_command", "command": "powershell -Command \"Get-PnpDevice -Class USB | Format-Table Status,Class,FriendlyName\""}

USER: show hardware info summary on linux
BOT: <think>
Getting a comprehensive hardware summary.
</think>
{"action": "run_command", "command": "sudo lshw -short 2>/dev/null || lscpu && echo '---' && free -h && echo '---' && lsblk"}

USER: show BIOS version on linux
BOT: <think>
Checking BIOS/firmware version.
</think>
{"action": "run_command", "command": "sudo dmidecode -t bios | head -20"}

USER: show BIOS version on windows
BOT: <think>
Checking BIOS version on Windows.
</think>
{"action": "run_command", "command": "powershell -Command \"Get-CimInstance Win32_BIOS | Format-List Manufacturer,SMBIOSBIOSVersion,ReleaseDate\""}

USER: check RAM details on linux
BOT: <think>
Showing detailed RAM module information.
</think>
{"action": "run_command", "command": "sudo dmidecode -t memory | grep -E 'Size|Speed|Type|Manufacturer' | head -20"}

USER: check RAM details on windows
BOT: <think>
Showing RAM module details on Windows.
</think>
{"action": "run_command", "command": "powershell -Command \"Get-CimInstance Win32_PhysicalMemory | Format-Table BankLabel,Capacity,Speed,Manufacturer\""}

# ── PACKAGE MANAGEMENT ADVANCED ──────────────────────────────────────────────

USER: search for a package called htop on ubuntu
BOT: <think>
Searching APT repositories for a package.
</think>
{"action": "apt", "command": "search htop"}

USER: show info about the nginx package on ubuntu
BOT: <think>
Showing detailed package information.
</think>
{"action": "apt", "command": "show nginx"}

USER: remove package vim on ubuntu
BOT: <think>
Removing a package on Ubuntu.
</think>
{"action": "apt", "command": "remove -y vim"}

USER: install multiple packages: git curl wget on ubuntu
BOT: <think>
Installing multiple packages at once.
</think>
{"action": "apt", "command": "install -y git curl wget"}

USER: add a PPA repository on ubuntu
BOT: <think>
Adding a PPA repository on Ubuntu.
</think>
{"action": "run_command", "command": "sudo add-apt-repository ppa:deadsnakes/ppa -y && sudo apt update"}

USER: install python 3.12 on ubuntu
BOT: <think>
Installing a specific Python version from deadsnakes PPA.
</think>
{"action": "run_command", "command": "sudo apt install -y python3.12 python3.12-venv"}

USER: search for vlc on winget
BOT: <think>
Searching Windows Package Manager for VLC.
</think>
{"action": "winget", "command": "search vlc"}

USER: install 7zip on windows
BOT: <think>
Installing 7-Zip via winget.
</think>
{"action": "winget", "command": "install 7zip.7zip"}

USER: uninstall a program on windows via winget
BOT: <think>
Uninstalling a program using winget.
</think>
{"action": "winget", "command": "uninstall --name \"Program Name\""}

USER: list all installed snap packages on ubuntu
BOT: <think>
Listing installed snap packages.
</think>
{"action": "run_command", "command": "snap list"}

USER: install a flatpak app on linux
BOT: <think>
Installing an app via Flatpak.
</think>
{"action": "run_command", "command": "flatpak install flathub org.gimp.GIMP -y"}

# ── DEVELOPER WORKFLOWS ─────────────────────────────────────────────────────

USER: create a python virtual environment
BOT: <think>
Creating a Python venv in the current directory.
</think>
{"action": "run_command", "command": "python3 -m venv venv"}

USER: activate the virtual environment on linux
BOT: <think>
Activating a venv needs to run in a visible terminal.
</think>
{"action": "open_terminal", "command": "source venv/bin/activate"}

USER: activate the virtual environment on windows
BOT: <think>
Activating a venv on Windows.
</think>
{"action": "open_terminal", "command": ".\\venv\\Scripts\\activate"}

USER: start a local python http server
BOT: <think>
Starting a simple HTTP server on port 8000.
</think>
{"action": "run_command", "command": "python3 -m http.server 8000"}

USER: start a node.js project from scratch
BOT: <think>
Initializing a new Node.js project.
</think>
{"action": "npm", "command": "init -y"}

USER: check for outdated npm packages
BOT: <think>
Checking for outdated npm dependencies.
</think>
{"action": "npm", "command": "outdated"}

USER: run database migrations
BOT: <think>
Running database migrations - this is typically a Python/Django command.
</think>
{"action": "run_command", "command": "python3 manage.py migrate"}

USER: connect to a postgres database
BOT: <think>
Opening a PostgreSQL shell in a terminal.
</think>
{"action": "open_terminal", "command": "psql -U postgres"}

USER: dump my mysql database
BOT: <think>
Creating a MySQL database backup.
</think>
{"action": "run_command", "command": "mysqldump -u root -p mydb > ~/Desktop/mydb_backup.sql"}

USER: start a redis server
BOT: <think>
Starting Redis server in a terminal.
</think>
{"action": "open_terminal", "command": "redis-server"}

USER: SSH into my server at 192.168.1.50
BOT: <think>
Opening an SSH session in a terminal.
</think>
{"action": "open_terminal", "command": "ssh user@192.168.1.50"}

USER: copy a file to remote server via SCP
BOT: <think>
The user wants to copy a file via SCP. I need more details.
</think>
{"action": "chat", "response": "I can help with that. Please provide the file path, remote user, server IP, and destination path. For example: 'scp ~/file.txt user@192.168.1.50:/home/user/'"}

USER: check docker container resource usage
BOT: <think>
Showing real-time Docker container resource stats.
</think>
{"action": "docker", "command": "stats --no-stream"}

USER: show docker container logs for the last 100 lines
BOT: <think>
Showing recent container logs.
</think>
{"action": "docker", "command": "logs --tail 100 mycontainer"}

USER: remove all stopped docker containers
BOT: <think>
Cleaning up stopped containers.
</think>
{"action": "docker", "command": "container prune -f"}

USER: remove unused docker images
BOT: <think>
Cleaning up dangling Docker images.
</think>
{"action": "docker", "command": "image prune -f"}

USER: enter a running docker container shell
BOT: <think>
Exec into a container needs interactive terminal.
</think>
{"action": "open_terminal", "command": "docker exec -it mycontainer /bin/bash"}

# ── ENVIRONMENT VARIABLES ───────────────────────────────────────────────────

USER: set environment variable API_KEY to abc123
BOT: <think>
Setting an environment variable using the set_env action.
</think>
{"action": "set_env", "key": "API_KEY", "value": "abc123"}

USER: set the NODE_ENV to production
BOT: <think>
Setting NODE_ENV environment variable.
</think>
{"action": "set_env", "key": "NODE_ENV", "value": "production"}

USER: set JAVA_HOME to /usr/lib/jvm/java-17
BOT: <think>
Setting the JAVA_HOME environment variable.
</think>
{"action": "set_env", "key": "JAVA_HOME", "value": "/usr/lib/jvm/java-17"}

USER: export DATABASE_URL=postgres://localhost/mydb
BOT: <think>
Setting a database connection string as environment variable.
</think>
{"action": "set_env", "key": "DATABASE_URL", "value": "postgres://localhost/mydb"}

# ── SYSTEM SETTINGS ─────────────────────────────────────────────────────────

USER: open system settings
BOT: <think>
Opening OS-native system settings panel.
</think>
{"action": "open_settings"}

USER: open settings
BOT: <think>
Opening the system settings application.
</think>
{"action": "open_settings"}

USER: open system preferences
BOT: <think>
The user wants to open system settings/preferences.
</think>
{"action": "open_settings"}

USER: go to computer settings
BOT: <think>
Opening the system settings panel.
</think>
{"action": "open_settings"}

USER: open control panel
BOT: <think>
The user wants system settings. I'll use open_settings which handles OS differences.
</think>
{"action": "open_settings"}

USER: open display settings on windows
BOT: <think>
Opening a specific Windows settings page.
</think>
{"action": "run_command", "command": "start ms-settings:display"}

USER: open sound settings on windows
BOT: <think>
Opening Windows sound settings.
</think>
{"action": "run_command", "command": "start ms-settings:sound"}

USER: open network settings on windows
BOT: <think>
Opening Windows network settings.
</think>
{"action": "run_command", "command": "start ms-settings:network"}

USER: open bluetooth settings on windows
BOT: <think>
Opening Windows bluetooth settings.
</think>
{"action": "run_command", "command": "start ms-settings:bluetooth"}

USER: open privacy settings on windows
BOT: <think>
Opening Windows privacy settings.
</think>
{"action": "run_command", "command": "start ms-settings:privacy"}

USER: open display settings on ubuntu
BOT: <think>
Opening GNOME display settings.
</think>
{"action": "run_command", "command": "gnome-control-center display"}

USER: open sound settings on ubuntu
BOT: <think>
Opening GNOME sound settings.
</think>
{"action": "run_command", "command": "gnome-control-center sound"}

USER: open network settings on ubuntu
BOT: <think>
Opening GNOME network settings.
</think>
{"action": "run_command", "command": "gnome-control-center network"}

# ── BACKUP & RECOVERY ───────────────────────────────────────────────────────

USER: backup my home directory to an external drive on linux
BOT: <think>
Creating a compressed backup of the home directory.
</think>
{"action": "run_command", "command": "tar -czf /media/$USER/backup/home_backup_$(date +%Y%m%d).tar.gz -C /home $USER"}

USER: create a system restore point on windows
BOT: <think>
Creating a Windows System Restore point.
</think>
{"action": "run_command", "command": "powershell -Command \"Checkpoint-Computer -Description 'Iris Backup' -RestorePointType 'MODIFY_SETTINGS'\""}

USER: rsync my documents to another folder
BOT: <think>
Syncing documents with rsync for incremental backup.
</think>
{"action": "run_command", "command": "rsync -avh --progress ~/Documents/ ~/Backup/Documents/"}

USER: backup my mysql database
BOT: <think>
Creating a MySQL database dump.
</think>
{"action": "run_command", "command": "mysqldump -u root --all-databases > ~/Desktop/all_databases_backup.sql"}

USER: backup postgres database
BOT: <think>
Creating a PostgreSQL database dump.
</think>
{"action": "run_command", "command": "pg_dump -U postgres mydb > ~/Desktop/mydb_backup.sql"}
