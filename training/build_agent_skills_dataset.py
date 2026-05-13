import os
import urllib.request
import re

# Output file where the new dataset will be stored
OUTPUT_FILE = "awesome_agent_skills.md"

# Hardcoded list of extremely high-value skills to download
# Format: (Skill Name, Raw GitHub URL)
SKILLS_TO_FETCH = [
    # Anthropic
    ("Anthropic PDF Skill", "https://raw.githubusercontent.com/anthropics/skills/main/skills/pdf/SKILL.md"),
    ("Anthropic DOCX Skill", "https://raw.githubusercontent.com/anthropics/skills/main/skills/docx/SKILL.md"),
    ("Anthropic Canvas Design", "https://raw.githubusercontent.com/anthropics/skills/main/skills/canvas-design/SKILL.md"),
    ("Anthropic Frontend Design", "https://raw.githubusercontent.com/anthropics/skills/main/skills/frontend-design/SKILL.md"),
    ("Anthropic Web Artifacts", "https://raw.githubusercontent.com/anthropics/skills/main/skills/web-artifacts-builder/SKILL.md"),
    ("Anthropic MCP Builder", "https://raw.githubusercontent.com/anthropics/skills/main/skills/mcp-builder/SKILL.md"),
    
    # Supabase
    ("Supabase Postgres Best Practices", "https://raw.githubusercontent.com/supabase/skills/main/skills/postgres-best-practices/SKILL.md"),
    
    # Stripe
    ("Stripe Integration Best Practices", "https://raw.githubusercontent.com/stripe/skills/main/skills/stripe-best-practices/SKILL.md"),
    
    # Callstack (React Native)
    ("React Native Best Practices", "https://raw.githubusercontent.com/callstackincubator/skills/main/skills/react-native-best-practices/SKILL.md"),
    ("React Native Upgrade Workflow", "https://raw.githubusercontent.com/callstackincubator/skills/main/skills/upgrading-react-native/SKILL.md"),
    
    # Better Auth
    ("Better Auth Best Practices", "https://raw.githubusercontent.com/better-auth/skills/main/skills/best-practices/SKILL.md"),
    
    # Tinybird
    ("Tinybird Best Practices", "https://raw.githubusercontent.com/tinybirdco/skills/main/skills/tinybird-best-practices/SKILL.md"),
    
    # HashiCorp (Terraform)
    ("Terraform Style Guide", "https://raw.githubusercontent.com/hashicorp/skills/main/skills/terraform-style-guide/SKILL.md"),
    
    # Neon Database
    ("Neon Postgres Best Practices", "https://raw.githubusercontent.com/neondatabase/skills/main/skills/neon-postgres/SKILL.md"),
    
    # Remotion
    ("Remotion Programmatic Video", "https://raw.githubusercontent.com/remotion-dev/skills/main/skills/remotion/SKILL.md"),
    
    # Vercel Labs
    ("Vercel React Best Practices", "https://raw.githubusercontent.com/vercel-labs/skills/main/skills/react-best-practices/SKILL.md"),
    ("Vercel Next.js Best Practices", "https://raw.githubusercontent.com/vercel-labs/skills/main/skills/next-best-practices/SKILL.md"),
    
    # Cloudflare
    ("Cloudflare Workers Best Practices", "https://raw.githubusercontent.com/cloudflare/skills/main/skills/workers-best-practices/SKILL.md"),
    
    # Netlify
    ("Netlify Functions", "https://raw.githubusercontent.com/netlify/skills/main/skills/netlify-functions/SKILL.md"),
]

import ssl

def clean_markdown(content: str) -> str:
    # Remove frontmatter if present
    content = re.sub(r'^---.*?---\n+', '', content, flags=re.DOTALL)
    return content.strip()

def build_dataset():
    print(f"Starting extraction of {len(SKILLS_TO_FETCH)} high-value Official Skills...")
    success_count = 0
    
    # Bypass SSL verification issues on some macOS Python installations
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for name, url in SKILLS_TO_FETCH:
            print(f"Fetching {name}...")
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
                    raw_content = response.read().decode('utf-8')
                    
                    cleaned = clean_markdown(raw_content)
                    if cleaned:
                        f.write(f"USER: What are the best practices or instructions for {name}?\n")
                        f.write(f"BOT: {cleaned}\n\n")
                        success_count += 1
                        print(f"  ✓ Success")
                    else:
                        print(f"  ✗ Failed: Empty content")
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                
    print(f"\nExtraction complete! Successfully downloaded {success_count}/{len(SKILLS_TO_FETCH)} skills into {OUTPUT_FILE}.")

if __name__ == "__main__":
    build_dataset()
