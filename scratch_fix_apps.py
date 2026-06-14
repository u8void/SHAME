import json
import subprocess
import shutil

def fix_config():
    c = json.load(open('config/control.conf'))
    apps = c.get('apps', {})
    CREATE_NO_WINDOW = 0x08000000
    
    for k, v in apps.items():
        if not shutil.which(v) and not v.startswith('ms-') and not v.startswith('shell:'):
            ps_cmd = f"$n='{k}'; Get-StartApps | Where-Object {{ $_.Name.ToLower().Contains($n.ToLower()) }} | Select-Object -First 1 AppID | ConvertTo-Json"
            res = subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            if res.returncode == 0 and res.stdout.strip():
                try:
                    data = json.loads(res.stdout)
                    if data and 'AppID' in data:
                        apps[k] = f"shell:AppsFolder\\{data['AppID']}"
                        print(f"Fixed {k} -> {apps[k]}")
                except:
                    pass
    
    json.dump(c, open('config/control.conf','w'), indent=2)
    print('Config apps updated successfully.')

if __name__ == "__main__":
    fix_config()
