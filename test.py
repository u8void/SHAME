
import src.controller as ctrl
# Force a simple shell command through the helper
res = ctrl._shell('echo hello')
print('Result:', res.stdout.strip())

