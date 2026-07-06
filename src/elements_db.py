import re
from typing import Dict, List, Optional

COLORS = {
    "neon": "Primary: cyan-400, Secondary: fuchsia-500, Background: zinc-950, Text: white. Use bright glowing text with drop-shadow-[0_0_15px_rgba(34,211,238,0.5)].",
    "pastel": "Primary: rose-300, Secondary: sky-300, Background: slate-50, Text: slate-800. Soft, gentle aesthetic.",
    "cyberpunk": "Primary: yellow-400, Secondary: cyan-400, Background: black, Text: zinc-100. High contrast, aggressive neon aesthetics.",
    "monochrome": "Primary: zinc-900, Secondary: zinc-500, Background: white, Text: black. Minimalist, high contrast grayscale.",
    "earth": "Primary: emerald-600, Secondary: amber-600, Background: stone-100, Text: stone-900. Natural, warm colors.",
    "ocean": "Primary: blue-500, Secondary: teal-400, Background: slate-900, Text: slate-50. Deep sea vibes.",
    "sunset": "Primary: orange-500, Secondary: rose-500, Background: stone-950, Text: stone-50. Warm evening gradients.",
    "luxury": "Primary: amber-300, Secondary: yellow-500, Background: zinc-950, Text: zinc-100. Gold accents on dark background.",
    "retro": "Primary: orange-400, Secondary: yellow-300, Background: amber-50, Text: brown-900. 70s/80s vintage feel.",
    "midnight": "Primary: indigo-500, Secondary: violet-500, Background: slate-950, Text: slate-300. Deep, quiet dark mode.",
    "crimson": "Primary: red-600, Secondary: rose-700, Background: neutral-950, Text: neutral-100. Deep bloody red vibes.",
    "forest": "Primary: green-700, Secondary: emerald-600, Background: stone-900, Text: stone-100. Dark wooded natural tones.",
    "sakura": "Primary: pink-400, Secondary: fuchsia-300, Background: pink-50, Text: slate-800. Cherry blossom inspired light theme.",
    "hacker": "Primary: green-500, Secondary: lime-400, Background: black, Text: green-500. Classic terminal hacker styling. Use font-mono.",
    "synthwave": "Primary: fuchsia-600, Secondary: purple-600, Background: indigo-950, Text: cyan-400. 80s outrun vaporwave style.",
    "dracula": "Primary: purple-500, Secondary: pink-500, Background: slate-900, Text: slate-200. Popular dark theme inspired.",
    "lavender": "Primary: violet-400, Secondary: purple-300, Background: slate-50, Text: slate-800. Soft purple aesthetic.",
    "volcanic": "Primary: red-600, Secondary: orange-500, Background: zinc-950, Text: zinc-100. Lava and dark rock aesthetics.",
    "arctic": "Primary: sky-300, Secondary: cyan-200, Background: slate-900, Text: slate-100. Cold, icy, dark aesthetic.",
    "candy": "Primary: pink-500, Secondary: yellow-400, Background: purple-50, Text: purple-900. Bright, sweet, and playful.",
    "cobalt": "Primary: blue-600, Secondary: indigo-500, Background: slate-900, Text: slate-100. Strong, deep metallic blues.",
    "magenta": "Primary: fuchsia-600, Secondary: pink-500, Background: neutral-950, Text: neutral-100. Bright, vibrant purple-pink.",
    "lime": "Primary: lime-500, Secondary: green-400, Background: stone-950, Text: stone-100. Sharp, acidic green tones.",
    "rose": "Primary: rose-500, Secondary: red-400, Background: rose-50, Text: rose-950. Soft but passionate red-pink.",
    "gold": "Primary: yellow-500, Secondary: amber-400, Background: zinc-900, Text: zinc-100. Rich, luxurious metallic yellow.",
    "silver": "Primary: slate-400, Secondary: gray-300, Background: slate-950, Text: slate-100. Cool, sleek metallic gray.",
    "bronze": "Primary: orange-700, Secondary: amber-600, Background: stone-900, Text: stone-100. Warm, rustic metallic brown.",
    "copper": "Primary: orange-500, Secondary: red-400, Background: zinc-900, Text: zinc-100. Bright, reddish metallic.",
    "ruby": "Primary: red-700, Secondary: rose-600, Background: neutral-950, Text: neutral-100. Deep, rich gem-like red.",
    "sapphire": "Primary: blue-700, Secondary: indigo-600, Background: slate-950, Text: slate-100. Deep, rich gem-like blue.",
    "emerald": "Primary: emerald-600, Secondary: green-500, Background: stone-950, Text: stone-100. Deep, rich gem-like green.",
    "amethyst": "Primary: purple-600, Secondary: fuchsia-500, Background: indigo-950, Text: indigo-100. Deep, rich gem-like purple.",
    "topaz": "Primary: amber-500, Secondary: orange-400, Background: stone-900, Text: stone-100. Bright, warm gem-like orange-yellow.",
    "onyx": "Primary: zinc-800, Secondary: neutral-700, Background: black, Text: zinc-300. Very dark, sleek black/gray.",
    "pearl": "Primary: slate-100, Secondary: gray-50, Background: white, Text: slate-800. Soft, slightly off-white light theme.",
    "obsidian": "Primary: slate-900, Secondary: zinc-800, Background: black, Text: slate-400. Glossy, extremely dark mode.",
    "ivory": "Primary: stone-200, Secondary: amber-50, Background: stone-50, Text: stone-800. Warm, off-white light theme.",
    "jade": "Primary: teal-600, Secondary: emerald-500, Background: slate-900, Text: slate-100. Muted, soft green tones.",
    "coral": "Primary: rose-400, Secondary: orange-400, Background: orange-50, Text: stone-900. Bright, tropical pink-orange.",
    "turquoise": "Primary: teal-400, Secondary: cyan-300, Background: slate-900, Text: slate-100. Bright, vibrant blue-green.",
    "maroon": "Primary: rose-900, Secondary: red-800, Background: stone-950, Text: stone-300. Very dark, muted red.",
    "navy": "Primary: slate-800, Secondary: blue-900, Background: slate-950, Text: slate-300. Very dark, professional blue.",
    "olive": "Primary: lime-800, Secondary: green-700, Background: stone-900, Text: stone-300. Muted, dark yellowish-green.",
    "peach": "Primary: orange-300, Secondary: rose-300, Background: orange-50, Text: stone-800. Soft, pale orange-pink.",
    "plum": "Primary: fuchsia-900, Secondary: purple-800, Background: slate-950, Text: slate-300. Dark, muted purple.",
    "red": "Primary: red-600, Secondary: red-500, Background: white, Text: neutral-900. Classic basic red.",
    "blue": "Primary: blue-600, Secondary: blue-500, Background: white, Text: neutral-900. Classic basic blue.",
    "green": "Primary: green-600, Secondary: green-500, Background: white, Text: neutral-900. Classic basic green.",
    "yellow": "Primary: yellow-500, Secondary: yellow-400, Background: neutral-900, Text: white. Classic basic yellow.",
    "orange": "Primary: orange-500, Secondary: orange-400, Background: white, Text: neutral-900. Classic basic orange.",
    "purple": "Primary: purple-600, Secondary: purple-500, Background: white, Text: neutral-900. Classic basic purple.",
    "pink": "Primary: pink-500, Secondary: pink-400, Background: white, Text: neutral-900. Classic basic pink.",
    "black": "Primary: black, Secondary: neutral-800, Background: white, Text: black. Classic basic black.",
    "white": "Primary: white, Secondary: neutral-100, Background: black, Text: white. Classic basic white.",
    "gray": "Primary: gray-500, Secondary: gray-400, Background: white, Text: neutral-900. Classic basic gray.",
    "brown": "Primary: amber-800, Secondary: amber-700, Background: amber-50, Text: amber-950. Classic basic brown.",
    "mint": "Primary: emerald-400, Secondary: teal-300, Background: stone-50, Text: stone-800. Cool, refreshing minty green.",
    "coffee": "Primary: amber-800, Secondary: stone-600, Background: stone-100, Text: stone-900. Warm, roasted coffee tones.",
    "matcha": "Primary: lime-700, Secondary: emerald-500, Background: stone-50, Text: stone-800. Gentle, organic Japanese green tea aesthetic.",
    "bubblegum": "Primary: pink-400, Secondary: sky-300, Background: pink-50, Text: pink-950. Sweet, playful, nostalgic pink and blue.",
    "lilac": "Primary: violet-300, Secondary: fuchsia-300, Background: slate-50, Text: slate-800. Soft, fragrant light purple tones.",
    "charcoal": "Primary: zinc-700, Secondary: zinc-500, Background: zinc-900, Text: zinc-100. Modern dark gray.",
    "cream": "Primary: amber-100, Secondary: yellow-100, Background: stone-50, Text: stone-900. Warm, soft off-white.",
    "sand": "Primary: yellow-600, Secondary: amber-700, Background: stone-100, Text: stone-900. Warm, desert-inspired tones.",
    "terracotta": "Primary: orange-700, Secondary: red-700, Background: stone-50, Text: stone-900. Earthen, clay-red pottery colors.",
    "nord": "Primary: sky-400, Secondary: blue-400, Background: slate-900, Text: slate-100. Clean, arctic nord-inspired dark theme.",
    "gruvbox": "Primary: yellow-600, Secondary: orange-600, Background: stone-900, Text: stone-200. Retro-technical warm dark theme.",
    "solarized-dark": "Primary: cyan-500, Secondary: blue-500, Background: slate-950, Text: slate-300. Classic low-contrast solarized dark.",
    "solarized-light": "Primary: blue-600, Secondary: cyan-600, Background: stone-100, Text: stone-800. Classic low-contrast solarized light.",
    "monokai": "Primary: pink-500, Secondary: yellow-400, Background: neutral-900, Text: white. Vibrant developer-editor inspired dark mode.",
    "one-dark": "Primary: blue-400, Secondary: magenta-400, Background: slate-900, Text: slate-200. Clean, professional editor dark mode.",
    "royal": "Primary: indigo-600, Secondary: yellow-500, Background: slate-950, Text: slate-100. Majestic dark blue and gold accents.",
    "burgundy": "Primary: red-800, Secondary: rose-900, Background: stone-950, Text: stone-200. Rich, deep wine-red palette.",
    "rust": "Primary: orange-800, Secondary: amber-900, Background: stone-950, Text: stone-200. Oxidized iron, rustic industrial colors.",
    "mustard": "Primary: yellow-600, Secondary: amber-500, Background: stone-900, Text: stone-100. Warm, sharp mustard yellow.",
    "sage": "Primary: emerald-700, Secondary: green-600, Background: stone-100, Text: stone-900. Muted, soft, herbal green.",
    "steel": "Primary: blue-400, Secondary: slate-400, Background: slate-950, Text: slate-100. Industrial metallic blue-gray.",
    "tropical": "Primary: emerald-400, Secondary: yellow-400, Background: teal-950, Text: white. Lush, vibrant tropical paradise.",
    "wine": "Primary: rose-800, Secondary: amber-700, Background: stone-950, Text: stone-200. Rich, aged wine and warm wood.",
    "galaxy": "Primary: violet-500, Secondary: indigo-400, Background: slate-950, Text: slate-100. Deep space nebula vibes with star-like accents.",
    "aqua": "Primary: cyan-500, Secondary: blue-400, Background: slate-50, Text: slate-900. Fresh water-inspired light theme.",
    "concrete": "Primary: stone-500, Secondary: zinc-400, Background: stone-200, Text: stone-900. Raw, urban concrete aesthetic.",
    "carbon": "Primary: zinc-600, Secondary: neutral-500, Background: neutral-950, Text: neutral-200. Carbon fiber dark tech look.",
    "cherry": "Primary: red-500, Secondary: pink-400, Background: red-50, Text: red-950. Sweet cherry blossom red-pink.",
    "denim": "Primary: blue-500, Secondary: indigo-400, Background: blue-50, Text: blue-950. Casual denim-inspired blue tones.",
    "honey": "Primary: amber-400, Secondary: yellow-300, Background: amber-50, Text: amber-950. Warm, golden honey sweetness.",
    "lavender-dark": "Primary: violet-400, Secondary: purple-500, Background: indigo-950, Text: indigo-100. Soft lavender on deep dark backdrop.",
    "mint-dark": "Primary: emerald-400, Secondary: teal-300, Background: emerald-950, Text: emerald-100. Cool mint on dark forest green.",
    "autumn": "Primary: orange-600, Secondary: red-600, Background: stone-100, Text: stone-900. Warm falling leaves and harvest tones.",
    "spring": "Primary: green-400, Secondary: pink-400, Background: green-50, Text: green-950. Fresh blossoms and new growth.",
    "winter": "Primary: blue-300, Secondary: slate-300, Background: slate-100, Text: slate-900. Cold, snowy, crisp winter whites.",
    "neon-pink": "Primary: pink-500, Secondary: fuchsia-400, Background: black, Text: pink-300. Hot neon pink on pure black.",
    "neon-green": "Primary: lime-400, Secondary: green-400, Background: black, Text: lime-300. Radioactive neon green on pure black.",
    "neon-blue": "Primary: blue-400, Secondary: cyan-400, Background: black, Text: blue-300. Electric neon blue on pure black.",
    "champagne": "Primary: amber-200, Secondary: yellow-100, Background: amber-50, Text: stone-800. Soft, bubbly champagne gold.",
    "titanium": "Primary: zinc-400, Secondary: slate-300, Background: zinc-900, Text: zinc-100. Brushed titanium metallic look.",
    "graphite": "Primary: neutral-600, Secondary: stone-500, Background: neutral-900, Text: neutral-200. Matte graphite pencil dark theme.",
    "mahogany": "Primary: red-900, Secondary: amber-800, Background: stone-950, Text: stone-200. Rich, dark wood grain tones.",
    "tiffany": "Primary: cyan-400, Secondary: teal-300, Background: white, Text: slate-900. Iconic Tiffany blue luxury.",
    "slate-blue": "Primary: slate-500, Secondary: blue-400, Background: slate-100, Text: slate-900. Muted, professional blue-gray.",
    "warm-gray": "Primary: stone-400, Secondary: stone-300, Background: stone-100, Text: stone-800. Cozy warm neutral grays.",
    "ice-blue": "Primary: sky-200, Secondary: blue-200, Background: white, Text: slate-800. Ultra-light frozen ice aesthetic."
}

ANIMATIONS = {
    "fade": """Add this to CSS:
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.animate-fade { animation: fadeIn 1s ease-in-out forwards; }""",
    "slide up": """Add this to CSS:
@keyframes slideUp { from { opacity: 0; transform: translateY(30px); } to { opacity: 1; transform: translateY(0); } }
.animate-slide-up { animation: slideUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards; }""",
    "slide in": """Add this to CSS:
@keyframes slideIn { from { opacity: 0; transform: translateX(-30px); } to { opacity: 1; transform: translateX(0); } }
.animate-slide-in { animation: slideIn 0.8s ease-out forwards; }""",
    "bounce": """Add this to CSS:
@keyframes bounce { 0%, 100% { transform: translateY(-25%); animation-timing-function: cubic-bezier(0.8,0,1,1); } 50% { transform: none; animation-timing-function: cubic-bezier(0,0,0.2,1); } }
.animate-bounce-custom { animation: bounce 1s infinite; }""",
    "pulse": """Add this to CSS:
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
.animate-pulse-custom { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }""",
    "spin": """Add this to CSS:
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.animate-spin-custom { animation: spin 1s linear infinite; }""",
    "float": """Add this to CSS:
@keyframes float { 0% { transform: translateY(0px); } 50% { transform: translateY(-10px); } 100% { transform: translateY(0px); } }
.animate-float { animation: float 3s ease-in-out infinite; }""",
    "glow": """Add this to CSS:
@keyframes glow { 0% { box-shadow: 0 0 5px currentColor; } 50% { box-shadow: 0 0 20px currentColor; } 100% { box-shadow: 0 0 5px currentColor; } }
.animate-glow { animation: glow 2s ease-in-out infinite; }""",
    "typewriter": """Add this to CSS:
@keyframes typing { from { width: 0 } to { width: 100% } }
@keyframes blink-caret { from, to { border-color: transparent } 50% { border-color: currentColor; } }
.animate-typewriter { overflow: hidden; white-space: nowrap; border-right: .15em solid; animation: typing 3.5s steps(40, end), blink-caret .75s step-end infinite; }""",
    "parallax": """For parallax effect, add `bg-fixed` to your background image container, and ensure it has `bg-cover bg-center`. Example: `class="bg-[url('...')] bg-fixed bg-cover bg-center"`.""",
    "zoom in": """Add this to CSS:
@keyframes zoomIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
.animate-zoom-in { animation: zoomIn 0.5s ease-out forwards; }""",
    "zoom out": """Add this to CSS:
@keyframes zoomOut { from { opacity: 1; transform: scale(1); } to { opacity: 0; transform: scale(0.9); } }
.animate-zoom-out { animation: zoomOut 0.5s ease-in forwards; }""",
    "flip": """Add this to CSS:
@keyframes flip { from { transform: perspective(400px) rotateY(0); } to { transform: perspective(400px) rotateY(180deg); } }
.animate-flip { animation: flip 0.6s ease-in-out forwards; }""",
    "shake": """Add this to CSS:
@keyframes shake { 0%, 100% { transform: translateX(0); } 10%, 30%, 50%, 70%, 90% { transform: translateX(-10px); } 20%, 40%, 60%, 80% { transform: translateX(10px); } }
.animate-shake { animation: shake 0.8s ease-in-out; }""",
    "wobble": """Add this to CSS:
@keyframes wobble { 0% { transform: translateX(0%); } 15% { transform: translateX(-25%) rotate(-5deg); } 30% { transform: translateX(20%) rotate(3deg); } 45% { transform: translateX(-15%) rotate(-3deg); } 60% { transform: translateX(10%) rotate(2deg); } 75% { transform: translateX(-5%) rotate(-1deg); } 100% { transform: translateX(0%); } }
.animate-wobble { animation: wobble 1s ease-in-out; }""",
    "heartbeat": """Add this to CSS:
@keyframes heartbeat { 0% { transform: scale(1); } 14% { transform: scale(1.3); } 28% { transform: scale(1); } 42% { transform: scale(1.3); } 70% { transform: scale(1); } }
.animate-heartbeat { animation: heartbeat 1.5s ease-in-out infinite; }""",
    "jello": """Add this to CSS:
@keyframes jello { 11.1% { transform: none } 22.2% { transform: skewX(-12.5deg) skewY(-12.5deg) } 33.3% { transform: skewX(6.25deg) skewY(6.25deg) } 44.4% { transform: skewX(-3.125deg) skewY(-3.125deg) } 55.5% { transform: skewX(1.5625deg) skewY(1.5625deg) } 66.6% { transform: skewX(-0.78125deg) skewY(-0.78125deg) } 77.7% { transform: skewX(0.390625deg) skewY(0.390625deg) } 88.8% { transform: skewX(-0.1953125deg) skewY(-0.1953125deg) } 100% { transform: none } }
.animate-jello { animation: jello 0.9s both; }""",
    "reveal": """Add this to CSS:
@keyframes reveal { 0% { clip-path: inset(0 100% 0 0); } 100% { clip-path: inset(0 0 0 0); } }
.animate-reveal { animation: reveal 1.2s cubic-bezier(0.77, 0, 0.175, 1) forwards; }""",
    "rubberband": """Add this to CSS:
@keyframes rubberBand { from { transform: scale3d(1, 1, 1); } 30% { transform: scale3d(1.25, 0.75, 1); } 40% { transform: scale3d(0.75, 1.25, 1); } 50% { transform: scale3d(1.15, 0.85, 1); } 65% { transform: scale3d(0.95, 1.05, 1); } 75% { transform: scale3d(1.05, 0.95, 1); } to { transform: scale3d(1, 1, 1); } }
.animate-rubberband { animation: rubberBand 1s; }""",
    "tada": """Add this to CSS:
@keyframes tada { from { transform: scale3d(1, 1, 1); } 10%, 20% { transform: scale3d(0.9, 0.9, 0.9) rotate3d(0, 0, 1, -3deg); } 30%, 50%, 70%, 90% { transform: scale3d(1.1, 1.1, 1.1) rotate3d(0, 0, 1, 3deg); } 40%, 60%, 80% { transform: scale3d(1.1, 1.1, 1.1) rotate3d(0, 0, 1, -3deg); } to { transform: scale3d(1, 1, 1); } }
.animate-tada { animation: tada 1s; }""",
    "swing": """Add this to CSS:
@keyframes swing { 20% { transform: rotate3d(0, 0, 1, 15deg); } 40% { transform: rotate3d(0, 0, 1, -10deg); } 60% { transform: rotate3d(0, 0, 1, 5deg); } 80% { transform: rotate3d(0, 0, 1, -5deg); } to { transform: rotate3d(0, 0, 1, 0deg); } }
.animate-swing { transform-origin: top center; animation: swing 1s; }""",
    "flash": """Add this to CSS:
@keyframes flash { from, 50%, to { opacity: 1; } 25%, 75% { opacity: 0; } }
.animate-flash { animation: flash 1s; }""",
    "headshake": """Add this to CSS:
@keyframes headShake { 0% { transform: translateX(0); } 6.5% { transform: translateX(-6px) rotateY(-9deg); } 18.5% { transform: translateX(5px) rotateY(7deg); } 31.5% { transform: translateX(-3px) rotateY(-5deg); } 43.5% { transform: translateX(2px) rotateY(3deg); } 50% { transform: translateX(0); } }
.animate-headshake { animation: headShake 1s ease-in-out; }""",
    "fade in up": """Add this to CSS:
@keyframes fadeInUp { from { opacity: 0; transform: translate3d(0, 100%, 0); } to { opacity: 1; transform: translate3d(0, 0, 0); } }
.animate-fade-in-up { animation: fadeInUp 1s; }""",
    "fade in down": """Add this to CSS:
@keyframes fadeInDown { from { opacity: 0; transform: translate3d(0, -100%, 0); } to { opacity: 1; transform: translate3d(0, 0, 0); } }
.animate-fade-in-down { animation: fadeInDown 1s; }""",
    "fade in left": """Add this to CSS:
@keyframes fadeInLeft { from { opacity: 0; transform: translate3d(-100%, 0, 0); } to { opacity: 1; transform: translate3d(0, 0, 0); } }
.animate-fade-in-left { animation: fadeInLeft 1s; }""",
    "fade in right": """Add this to CSS:
@keyframes fadeInRight { from { opacity: 0; transform: translate3d(100%, 0, 0); } to { opacity: 1; transform: translate3d(0, 0, 0); } }
.animate-fade-in-right { animation: fadeInRight 1s; }""",
    "rotate in": """Add this to CSS:
@keyframes rotateIn { from { transform-origin: center; transform: rotate3d(0, 0, 1, -200deg); opacity: 0; } to { transform-origin: center; transform: translate3d(0, 0, 0); opacity: 1; } }
.animate-rotate-in { animation: rotateIn 1s; }""",
    "rotate out": """Add this to CSS:
@keyframes rotateOut { from { transform-origin: center; opacity: 1; } to { transform-origin: center; transform: rotate3d(0, 0, 1, 200deg); opacity: 0; } }
.animate-rotate-out { animation: rotateOut 1s; }""",
    "hinge": """Add this to CSS:
@keyframes hinge { 0% { transform-origin: top left; animation-timing-function: ease-in-out; } 20%, 60% { transform: rotate3d(0, 0, 1, 80deg); transform-origin: top left; animation-timing-function: ease-in-out; } 40%, 80% { transform: rotate3d(0, 0, 1, 60deg); transform-origin: top left; animation-timing-function: ease-in-out; opacity: 1; } to { transform: translate3d(0, 700px, 0); opacity: 0; } }
.animate-hinge { animation: hinge 2s; }""",
    "roll in": """Add this to CSS:
@keyframes rollIn { from { opacity: 0; transform: translate3d(-100%, 0, 0) rotate3d(0, 0, 1, -120deg); } to { opacity: 1; transform: translate3d(0, 0, 0); } }
.animate-roll-in { animation: rollIn 1s; }""",
    "roll out": """Add this to CSS:
@keyframes rollOut { from { opacity: 1; } to { opacity: 0; transform: translate3d(100%, 0, 0) rotate3d(0, 0, 1, 120deg); } }
.animate-roll-out { animation: rollOut 1s; }""",
    "zoom in up": """Add this to CSS:
@keyframes zoomInUp { from { opacity: 0; transform: scale3d(0.1, 0.1, 0.1) translate3d(0, 1000px, 0); animation-timing-function: cubic-bezier(0.55, 0.055, 0.675, 0.19); } 60% { opacity: 1; transform: scale3d(0.475, 0.475, 0.475) translate3d(0, -60px, 0); animation-timing-function: cubic-bezier(0.175, 0.885, 0.32, 1); } }
.animate-zoom-in-up { animation: zoomInUp 1s; }""",
    "zoom in down": """Add this to CSS:
@keyframes zoomInDown { from { opacity: 0; transform: scale3d(0.1, 0.1, 0.1) translate3d(0, -1000px, 0); animation-timing-function: cubic-bezier(0.55, 0.055, 0.675, 0.19); } 60% { opacity: 1; transform: scale3d(0.475, 0.475, 0.475) translate3d(0, 60px, 0); animation-timing-function: cubic-bezier(0.175, 0.885, 0.32, 1); } }
.animate-zoom-in-down { animation: zoomInDown 1s; }""",
    "glitch": """Add this to CSS:
@keyframes glitch { 0% { clip-path: inset(40% 0 61% 0); } 20% { clip-path: inset(92% 0 1% 0); } 40% { clip-path: inset(25% 0 58% 0); } 60% { clip-path: inset(80% 0 5% 0); } 80% { clip-path: inset(11% 0 80% 0); } 100% { clip-path: inset(50% 0 30% 0); } }
.animate-glitch { animation: glitch 1s linear infinite alternate-reverse; }""",
    "rotate": """Add this to CSS:
@keyframes rotate3d { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.animate-rotate { animation: rotate3d 10s linear infinite; }""",
    "shimmer": """Add this to CSS:
@keyframes shimmer { 100% { transform: translateX(100%); } }
.animate-shimmer { position: relative; overflow: hidden; }
.animate-shimmer::after { position: absolute; top: 0; right: 0; bottom: 0; left: 0; transform: translateX(-100%); background-image: linear-gradient(90deg, rgba(255, 255, 255, 0) 0%, rgba(255, 255, 255, 0.2) 20%, rgba(255, 255, 255, 0.5) 60%, rgba(255, 255, 255, 0) 100%); animation: shimmer 2s infinite; content: ''; }""",
    "wave": """Add this to CSS:
@keyframes wave { 0%, 100% { transform: rotate(0deg); } 50% { transform: rotate(15deg); } }
.animate-wave { transform-origin: bottom right; animation: wave 1.5s ease-in-out infinite; }""",
    "heartbeat slow": """Add this to CSS:
@keyframes heartbeatSlow { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.05); } }
.animate-heartbeat-slow { animation: heartbeatSlow 3s ease-in-out infinite; }""",
    "skew": """Add this to CSS:
@keyframes skew { 0%, 100% { transform: skewX(0); } 50% { transform: skewX(-10deg); } }
.animate-skew { animation: skew 2s ease-in-out infinite; }""",
    "blur in": """Add this to CSS:
@keyframes blurIn { from { filter: blur(10px); opacity: 0; } to { filter: blur(0); opacity: 1; } }
.animate-blur-in { animation: blurIn 0.8s ease-out forwards; }""",
    "blur out": """Add this to CSS:
@keyframes blurOut { from { filter: blur(0); opacity: 1; } to { filter: blur(10px); opacity: 0; } }
.animate-blur-out { animation: blurOut 0.8s ease-in forwards; }""",
    "slide out up": """Add this to CSS:
@keyframes slideOutUp { from { opacity: 1; transform: translateY(0); } to { opacity: 0; transform: translateY(-30px); } }
.animate-slide-out-up { animation: slideOutUp 0.8s ease-in forwards; }""",
    "slide out down": """Add this to CSS:
@keyframes slideOutDown { from { opacity: 1; transform: translateY(0); } to { opacity: 0; transform: translateY(30px); } }
.animate-slide-out-down { animation: slideOutDown 0.8s ease-in forwards; }""",
    "slide out left": """Add this to CSS:
@keyframes slideOutLeft { from { opacity: 1; transform: translateX(0); } to { opacity: 0; transform: translateX(-30px); } }
.animate-slide-out-left { animation: slideOutLeft 0.8s ease-in forwards; }""",
    "slide out right": """Add this to CSS:
@keyframes slideOutRight { from { opacity: 1; transform: translateX(0); } to { opacity: 0; transform: translateX(30px); } }
.animate-slide-out-right { animation: slideOutRight 0.8s ease-in forwards; }""",
    "rotate in down left": """Add this to CSS:
@keyframes rotateInDownLeft { from { transform-origin: left bottom; transform: rotate3d(0, 0, 1, -45deg); opacity: 0; } to { transform-origin: left bottom; transform: translate3d(0, 0, 0); opacity: 1; } }
.animate-rotate-in-down-left { animation: rotateInDownLeft 1s; }""",
    "rotate in down right": """Add this to CSS:
@keyframes rotateInDownRight { from { transform-origin: right bottom; transform: rotate3d(0, 0, 1, 45deg); opacity: 0; } to { transform-origin: right bottom; transform: translate3d(0, 0, 0); opacity: 1; } }
.animate-rotate-in-down-right { animation: rotateInDownRight 1s; }""",
    "bounce in": """Add this to CSS:
@keyframes bounceIn { from, 20%, 40%, 60%, 80%, to { animation-timing-function: cubic-bezier(0.215, 0.61, 0.355, 1); } 0% { opacity: 0; transform: scale3d(0.3, 0.3, 0.3); } 20% { transform: scale3d(1.1, 1.1, 1.1); } 40% { transform: scale3d(0.9, 0.9, 0.9); } 60% { opacity: 1; transform: scale3d(1.03, 1.03, 1.03); } 80% { transform: scale3d(0.97, 0.97, 0.97); } to { opacity: 1; transform: scale3d(1, 1, 1); } }
.animate-bounce-in { animation: bounceIn 0.8s; }""",
    "bounce out": """Add this to CSS:
@keyframes bounceOut { 20% { transform: scale3d(0.9, 0.9, 0.9); } 50%, 55% { opacity: 1; transform: scale3d(1.1, 1.1, 1.1); } to { opacity: 0; transform: scale3d(0.3, 0.3, 0.3); } }
.animate-bounce-out { animation: bounceOut 0.8s; }"""
}

STYLES = {
    "glassmorphism": "Use `bg-white/10 backdrop-blur-lg border border-white/20 shadow-[0_8px_32px_0_rgba(31,38,135,0.37)]` for cards and containers.",
    "brutalism": "Use harsh borders and high contrast: `border-4 border-black bg-white shadow-[8px_8px_0px_0px_rgba(0,0,0,1)] hover:translate-y-[2px] hover:translate-x-[2px] hover:shadow-[6px_6px_0px_0px_rgba(0,0,0,1)] transition-all font-mono`.",
    "neumorphism": "Use soft UI elements on a colored background. Example for a light gray bg (`bg-gray-200`): `bg-gray-200 shadow-[20px_20px_60px_#cacaca,-20px_-20px_60px_#f6f6f6] rounded-2xl`.",
    "minimalist": "Extremely clean, lots of whitespace (`p-12`, `gap-8`), simple typography, no borders, subtle off-white or gray backgrounds.",
    "wireframe": "Use `border border-dashed border-zinc-400 bg-transparent` for everything, showing the skeletal structure of the site.",
    "claymorphism": "Soft, 3D clay-like effect. Use `bg-white rounded-3xl shadow-[inset_-10px_-10px_20px_rgba(0,0,0,0.1),_10px_10px_20px_rgba(0,0,0,0.1)]`.",
    "material": "Google Material Design inspired. Use prominent box shadows, distinct layers, card-based layouts. `bg-white shadow-md rounded hover:shadow-lg transition-shadow`.",
    "flat": "No shadows, no gradients, 2D minimalist feel. Solid colors, sharp edges or simple rounded corners. Example: `bg-blue-500 text-white rounded-none border-none`.",
    "bauhaus": "Primary colors (red, yellow, blue), geometric shapes (circles, squares, triangles), strong diagonal lines, heavy black borders. `bg-yellow-400 border-8 border-black p-8 rounded-full`.",
    "retro-futurism": "Think fallout terminals or old sci-fi interfaces. Amber or green text on dark screens, CRT scanline effects, grid backgrounds.",
    "neo-brutalism": "Like brutalism but with softer colors, often pastels paired with harsh black borders and offset shadows. `border-2 border-black bg-pink-300 shadow-[4px_4px_0px_0px_rgba(0,0,0,1)] rounded-lg`.",
    "cyber": "Glitch effects, neon glows, angled borders. `border border-cyan-500 bg-black/50 text-cyan-400 uppercase tracking-widest relative` with glowing drop shadows.",
    "kawaii": "Cute, bubbly, soft shapes, pastel pinks/purples, rounded fonts, lots of emojis or cute icons. `bg-pink-100 border-pink-300 rounded-3xl p-6 shadow-sm`.",
    "corporate": "Professional, clean, trustworthy. Blue and slate palettes, very legible sans-serif fonts, subtle gray borders. `bg-white border border-gray-200 shadow-sm text-gray-800`.",
    "fluent": "Microsoft Fluent Design inspired. Acrylic blur effects, soft light/shadows, rounded corners. Use `backdrop-blur-xl bg-white/70 shadow-lg`.",
    "metro": "Windows 8 Metro style. Flat, brightly colored square tiles, stark typography, no rounded corners, no shadows. Use `rounded-none shadow-none`.",
    "nordic": "Scandinavian minimalism. Extremely muted earthy tones, lots of white space, thin elegant fonts. Use `bg-stone-50 text-stone-700`.",
    "gothic": "Dark, moody, ornate. Use serif fonts, deep reds and blacks, subtle dark textures or borders. Use `font-serif bg-zinc-950 text-zinc-300 border-double border-zinc-800`.",
    "steampunk": "Victorian sci-fi. Brass/copper colors, gear motifs, old paper textures, serif/typewriter fonts. Use `bg-[url('paper-texture.jpg')] bg-amber-50 border-amber-800 text-stone-900`.",
    "vaporwave": "Retro 80s aesthetics. Gradients of cyan and magenta, grid backgrounds, pixel fonts, classical statue imagery. Use `bg-gradient-to-br from-cyan-400 to-fuchsia-500`.",
    "retrowave": "Outrun 80s synthwave style. Neon pink/blue on pure black, grid floors, glowing text. Use `bg-black text-cyan-400 drop-shadow-[0_0_8px_rgba(34,211,238,0.8)]`.",
    "grunge": "Distressed textures, dirty colors, chaotic layouts, rough edges. Use messy borders, dark grays and browns.",
    "holographic": "Iridescent, multi-color gradients shifting smoothly. Use `bg-gradient-to-r from-pink-300 via-purple-300 to-indigo-400 animate-gradient-x`.",
    "biomorphic": "Organic, flowing shapes, abstract blobs instead of rectangles. Use heavy `border-radius: 40% 60% 70% 30% / 40% 50% 60% 50%` for blob shapes.",
    "memphis": "80s Memphis group design. Squiggles, geometric shapes, bold clashing colors, distinct black outlines. Use `border-4 border-black` with bright yellow/pink/blue fills.",
    "isometric": "Faux 3D perspective using CSS transforms. Use `transform: rotateX(60deg) rotateZ(-45deg)` to create an isometric grid feel.",
    "pop art": "Comic book style, halftone dots, thick black borders, primary colors, bold action fonts. Use heavy outlines and high contrast.",
    "psychedelic": "Trippy, swirling patterns, extremely saturated clashing colors, distorted typography. Use intense gradients and warped shapes.",
    "glassmorphism-dark": "Use dark glass aesthetic: `bg-black/30 backdrop-blur-md border border-white/10 shadow-[0_8px_32px_0_rgba(0,0,0,0.5)]` for modern stealth widgets.",
    "skeuomorphic": "Classic old iOS/macOS realistic style. Heavy gradients, inner shadows, glossy overlays, and distinct borders: `bg-gradient-to-b from-gray-100 to-gray-300 border border-gray-400 rounded-lg shadow-[inset_0_1px_0_rgba(255,255,255,0.6),_0_2px_4px_rgba(0,0,0,0.15)]`.",
    "origami": "Folded paper aesthetic. Sharp polygon shapes, stark shadows, and high contrast angled segments: `bg-white border-b-4 border-r-4 border-slate-300 shadow-sm hover:shadow-md transition-shadow`.",
    "acid-grime": "Toxic cyberpunk hybrid. Clashing acid green and deep purples, dirty borders, scanlines, and extreme text shadow glows.",
    "techwear": "Tactical, functional, and tech-focused. Heavy black webbing lines, tiny utility tags, monospaced tech fonts, and modular card widgets: `border-2 border-zinc-700 bg-zinc-950 p-4 font-mono text-xs uppercase tracking-wider`.",
    "solarized": "Highly accessible, low-contrast mathematical feel. Solid colored background using slate-900 or stone-100, matching perfectly with clean, elegant layout shapes.",
    "terminal": "Ultra-minimal monospaced hacker theme: `font-mono bg-black text-green-400 border border-green-500/50 p-4 rounded`.",
    "chalkboard": "Handwritten style. Slate-800 or green-900 background with white dashed outlines and informal/chalky text accents: `bg-emerald-950 border-4 border-amber-800 text-stone-100 rounded-lg shadow-inner`.",
    "glitch-art": "Broken digital aesthetic. Shifted red/blue text shadows, absolute-positioned offset copies, and jagged clipping masks.",
    "cyber-grid": "Futuristic neon wireframe. Deep indigo/black background with a grid background overlay and glowing cyan/purple borders: `bg-grid bg-slate-950 border border-cyan-500 shadow-[0_0_10px_rgba(6,182,212,0.3)]`.",
    "pixel-art": "Nostalgic 8-bit grid style. Thick pixelated borders, retro game colors, and custom pixel-based typography: `border-4 border-black bg-stone-100 [image-rendering:pixelated]`.",
    "art-deco": "1920s luxury geometric. Intricate gold geometric borders, thin elegant serif fonts, and high contrast dark marble backgrounds: `font-serif bg-zinc-950 text-amber-400 border-double border-4 border-amber-400`.",
    "cottage-core": "Cozy, rural, romantic aesthetic. Warm earthy tones, floral patterns, handwritten fonts, soft shadows, and rounded organic shapes: `bg-amber-50 border border-amber-200 rounded-2xl shadow-sm font-serif text-stone-800`.",
    "afrofuturism": "Bold, futuristic African-inspired design. Rich golds, deep purples, geometric tribal patterns, and bold display fonts: `bg-indigo-950 text-amber-400 border-2 border-amber-500 font-bold`.",
    "y2k": "Early 2000s web nostalgia. Bubbly gradients, metallic chrome effects, star motifs, and bold sans-serif fonts: `bg-gradient-to-br from-pink-300 via-purple-200 to-blue-300 rounded-2xl shadow-lg`.",
    "dark-academia": "Scholarly, intellectual dark aesthetic. Deep browns, muted golds, serif typography, old book textures: `bg-stone-900 text-amber-100 font-serif border border-amber-900/30`.",
    "light-academia": "Bright scholarly aesthetic. Cream backgrounds, warm browns, serif fonts, structured layouts: `bg-amber-50 text-stone-800 font-serif border border-stone-200`.",
    "solarpunk": "Optimistic green-tech future. Bright greens, solar yellows, organic curves, and clean modern layouts: `bg-emerald-50 text-emerald-900 border border-emerald-200 rounded-xl`.",
    "cyberdelic": "Psychedelic meets cyberpunk. Neon gradients, fractal patterns, trippy animations, and bold geometric shapes: `bg-black text-fuchsia-400 border border-fuchsia-500/50 shadow-[0_0_20px_rgba(217,70,239,0.3)]`.",
    "maximalist": "More is more. Layer patterns, mix fonts, clash colors intentionally, fill every space with rich visual detail and ornate decoration.",
    "japandi": "Japanese-Scandinavian fusion. Ultra-minimal, natural wood tones, muted earth colors, clean lines, and zen-like whitespace: `bg-stone-50 text-stone-700 border-b border-stone-200`.",
    "wabi-sabi": "Embrace imperfection. Organic textures, muted earthy tones, asymmetric layouts, and raw unfinished edges: `bg-stone-100 text-stone-600 rounded-none border border-stone-300`.",
    "tropical-deco": "Art Deco meets tropical. Palm leaf motifs, emerald and gold, geometric borders, and lush backgrounds: `bg-emerald-900 text-amber-300 border-2 border-amber-400 font-serif`.",
    "dark-luxury": "Ultra-premium dark. Matte black, subtle gold accents, thin elegant fonts, and generous spacing: `bg-black text-amber-200 font-light tracking-widest border-b border-amber-400/20`.",
    "eco": "Environmental sustainability theme. Natural greens, recycled paper textures, organic shapes, and earthy warm tones: `bg-lime-50 text-green-900 border border-green-200 rounded-lg`.",
    "paper-cut": "Layered paper cutout aesthetic. Distinct shadow layers, solid colors, no gradients, and stacked depth: `bg-white shadow-[0_4px_0_0_rgba(0,0,0,0.1),0_8px_0_0_rgba(0,0,0,0.05)] rounded-lg`.",
    "watercolor": "Soft, painted watercolor aesthetic. Blurred edges, pastel washes, delicate typography, and artistic splatter accents.",
    "stained-glass": "Cathedral stained glass. Bold black outlines, vibrant jewel-tone fills, geometric segmented panels: `border-4 border-black bg-gradient-to-br from-red-500 via-blue-500 to-green-500`.",
    "blueprint": "Technical blueprint style. Deep blue background, white/cyan thin lines, monospace font, and grid overlay: `bg-blue-900 text-cyan-100 font-mono border border-cyan-400/30`.",
    "comic-book": "Bold comic panel style. Thick black outlines, halftone dots, speech bubbles, POW/ZAP action text, and primary colors: `border-4 border-black bg-yellow-300 font-black uppercase`.",
    "sci-fi-hud": "Heads-up display interface. Transparent panels, scanning lines, circular UI elements, and cyan/amber data readouts: `bg-black/80 border border-cyan-500/40 text-cyan-400 font-mono text-sm`.",
    "crypto-web3": "Blockchain/Web3 aesthetic. Dark purple-black backgrounds, neon gradient accents, hexagonal shapes, and futuristic sans-serif fonts: `bg-slate-950 text-purple-300 border border-purple-500/20`."
}

EFFECTS = {
    "blur": "Use `blur-sm`, `blur-md`, or `blur-lg` utility classes for standard blur, and `backdrop-blur-md` for glassmorphism effects.",
    "heavy blur": "Use `blur-xl` or `blur-2xl` for very strong blur effects, or `backdrop-blur-xl` for heavy glassmorphism.",
    "light blur": "Use `blur-sm` or `backdrop-blur-sm` for subtle blur effects.",
    "shadow": "Use standard Tailwind shadow utilities: `shadow-md`, `shadow-lg`, `shadow-xl`, or `shadow-2xl` for depth.",
    "glow": "Use drop shadows with colors, e.g., `drop-shadow-[0_0_15px_rgba(255,255,255,0.5)]` or `shadow-[0_0_20px_theme('colors.primary.500')]`.",
    "rounded": "Use `rounded-md`, `rounded-lg`, `rounded-xl`, `rounded-2xl`, or `rounded-full` for border radius.",
    "sharp edges": "Ensure elements use `rounded-none` for completely sharp square corners.",
    "gradient text": "Use `bg-clip-text text-transparent bg-gradient-to-r` followed by standard `from-x to-y` colors.",
    "gradient background": "Use `bg-gradient-to-r`, `bg-gradient-to-br`, or `bg-gradient-to-t` with appropriate `from-` and `to-` colors.",
    "glass": "Use `bg-white/10 backdrop-blur-lg border border-white/20` for a glass effect.",
    "inner shadow": "Use `shadow-[inset_0_2px_4px_rgba(0,0,0,0.06)]` or custom inset shadows for deep carved interfaces.",
    "grid overlay": "Use a subtle dot or grid background pattern: `bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:24px_24px]`.",
    "neon border": "Use a colorful glowing border: `border border-cyan-400 shadow-[0_0_10px_#22d3ee]`.",
    "text shadow": "Use custom text shadow utilities or standard inline CSS `text-shadow: 0 0 8px currentColor` for glowing typography.",
    "scanline": "Use a repeating scanline gradient overlay to simulate retro CRT screens: `bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[size:100%_4px,3px_100%]`.",
    "noise": "Use a grainy noise SVG or CSS background overlay to add depth and organic paper/digital feel.",
    "mask fade": "Use a CSS mask-image gradient to smoothly fade out edges: `[mask-image:linear-gradient(to_bottom,white_60%,transparent)]`.",
    "mirror reflection": "Use Webkit box reflection or a gradient mirror overlay under elements for a shiny premium display floor effect.",
    "chromatic aberration": "Use slight red/cyan offset shadow overlays on text/images to simulate lens distortion.",
    "frosted glass": "Use `backdrop-blur-xl bg-white/5 border border-white/10` for a deep frosted glass panel effect.",
    "emboss": "Use `shadow-[inset_1px_1px_2px_rgba(255,255,255,0.3),inset_-1px_-1px_2px_rgba(0,0,0,0.3)]` for raised embossed elements.",
    "deboss": "Use `shadow-[inset_2px_2px_5px_rgba(0,0,0,0.2),inset_-2px_-2px_5px_rgba(255,255,255,0.1)]` for pressed-in debossed elements.",
    "parallax bg": "Use `bg-fixed bg-cover bg-center` on a full-width background image container for a parallax scrolling effect.",
    "dotted bg": "Use `bg-[radial-gradient(circle,_#00000010_1px,_transparent_1px)] bg-[size:20px_20px]` for a subtle dot pattern background.",
    "gradient border": "Use `bg-gradient-to-r from-cyan-500 to-purple-500 p-[1px] rounded-xl` as a wrapper, with a solid bg inner div for gradient borders.",
    "long shadow": "Use `shadow-[5px_5px_0_rgba(0,0,0,0.2),10px_10px_0_rgba(0,0,0,0.1)]` for retro flat long shadows.",
    "outline text": "Use `-webkit-text-stroke: 1px white; color: transparent;` via inline style for outlined/hollow text.",
    "duotone": "Use `mix-blend-mode: multiply` with a colored overlay on images for a duotone photo effect.",
    "vignette": "Use `shadow-[inset_0_0_100px_rgba(0,0,0,0.5)]` on an image container for a vignette darkened-edge effect.",
    "halftone": "Use `bg-[radial-gradient(circle,_black_1px,_transparent_1px)] bg-[size:8px_8px]` for a comic-book halftone dot pattern.",
    "striped bg": "Use `bg-[repeating-linear-gradient(45deg,transparent,transparent_10px,rgba(0,0,0,0.05)_10px,rgba(0,0,0,0.05)_20px)]` for diagonal stripes.",
    "border glow": "Use `border border-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.4),inset_0_0_15px_rgba(6,182,212,0.1)]` for glowing borders.",
    "clip path": "Use `clip-path: polygon(...)` for custom non-rectangular shapes like triangles, hexagons, or diagonal cuts.",
    "sticky element": "Use `sticky top-0 z-50` to make an element stick to the top of the viewport on scroll."
}

TYPOGRAPHY = {
    "sans": "Use `font-family: 'Inter', sans-serif`. Clean, modern, highly legible sans-serif. Add `<link href='https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "serif": "Use `font-family: 'Playfair Display', serif`. Elegant, editorial serif font. Add `<link href='https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "mono": "Use `font-family: 'JetBrains Mono', monospace`. Developer/hacker monospace font. Add `<link href='https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap' rel='stylesheet'>`.",
    "display": "Use `font-family: 'Outfit', sans-serif`. Bold, geometric display font for headlines. Add `<link href='https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "handwritten": "Use `font-family: 'Caveat', cursive`. Casual handwritten script. Add `<link href='https://fonts.googleapis.com/css2?family=Caveat:wght@400;500;600;700&display=swap' rel='stylesheet'>`.",
    "rounded": "Use `font-family: 'Nunito', sans-serif`. Friendly rounded sans-serif. Add `<link href='https://fonts.googleapis.com/css2?family=Nunito:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "elegant": "Use `font-family: 'Cormorant Garamond', serif`. Thin, sophisticated serif for luxury. Add `<link href='https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@300;400;500;600;700&display=swap' rel='stylesheet'>`.",
    "bold": "Use `font-family: 'Space Grotesk', sans-serif`. Strong geometric font for tech/startup. Add `<link href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&display=swap' rel='stylesheet'>`.",
    "retro": "Use `font-family: 'Press Start 2P', cursive`. Pixelated retro gaming font. Add `<link href='https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap' rel='stylesheet'>`.",
    "slab": "Use `font-family: 'Roboto Slab', serif`. Strong slab-serif for headlines. Add `<link href='https://fonts.googleapis.com/css2?family=Roboto+Slab:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "futuristic": "Use `font-family: 'Orbitron', sans-serif`. Geometric, sci-fi inspired display font. Add `<link href='https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "typewriter": "Use `font-family: 'Special Elite', cursive`. Old typewriter style. Add `<link href='https://fonts.googleapis.com/css2?family=Special+Elite&display=swap' rel='stylesheet'>`.",
    "condensed": "Use `font-family: 'Barlow Condensed', sans-serif`. Tall narrow font for sporty/news. Add `<link href='https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "arabic": "Use `font-family: 'Cairo', sans-serif`. Modern Arabic-supporting font. Add `<link href='https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "minimal": "Use `font-family: 'DM Sans', sans-serif`. Ultra-clean minimalist sans. Add `<link href='https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&display=swap' rel='stylesheet'>`.",
    "geometric": "Use `font-family: 'Poppins', sans-serif`. Clean geometric sans for modern sites. Add `<link href='https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "editorial": "Use `font-family: 'Lora', serif`. Beautiful editorial serif for blogs/magazines. Add `<link href='https://fonts.googleapis.com/css2?family=Lora:wght@400;500;600;700&display=swap' rel='stylesheet'>`.",
    "tech": "Use `font-family: 'IBM Plex Sans', sans-serif`. Professional tech-company font. Add `<link href='https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap' rel='stylesheet'>`.",
    "luxury": "Use `font-family: 'Cinzel', serif`. Regal, luxury display serif. Add `<link href='https://fonts.googleapis.com/css2?family=Cinzel:wght@400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "playful": "Use `font-family: 'Fredoka', sans-serif`. Bubbly, friendly rounded font. Add `<link href='https://fonts.googleapis.com/css2?family=Fredoka:wght@300;400;500;600;700&display=swap' rel='stylesheet'>`.",
    "newspaper": "Use `font-family: 'Merriweather', serif`. Classic newspaper serif for long reading. Add `<link href='https://fonts.googleapis.com/css2?family=Merriweather:wght@300;400;700;900&display=swap' rel='stylesheet'>`.",
    "gothic-font": "Use `font-family: 'Cinzel Decorative', cursive`. Ornate gothic display font. Add `<link href='https://fonts.googleapis.com/css2?family=Cinzel+Decorative:wght@400;700;900&display=swap' rel='stylesheet'>`.",
    "wide": "Use `font-family: 'Raleway', sans-serif`. Elegant wide-set thin sans-serif. Add `<link href='https://fonts.googleapis.com/css2?family=Raleway:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "script": "Use `font-family: 'Dancing Script', cursive`. Flowing calligraphy script. Add `<link href='https://fonts.googleapis.com/css2?family=Dancing+Script:wght@400;500;600;700&display=swap' rel='stylesheet'>`.",
    "modern-serif": "Use `font-family: 'DM Serif Display', serif`. Modern, elegant serif for headlines. Add `<link href='https://fonts.googleapis.com/css2?family=DM+Serif+Display&display=swap' rel='stylesheet'>`.",
    "grotesk": "Use `font-family: 'Darker Grotesque', sans-serif`. Edgy modern grotesk for creative sites. Add `<link href='https://fonts.googleapis.com/css2?family=Darker+Grotesque:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`.",
    "code": "Use `font-family: 'Fira Code', monospace`. Monospace with ligatures for code. Add `<link href='https://fonts.googleapis.com/css2?family=Fira+Code:wght@300;400;500;600;700&display=swap' rel='stylesheet'>`.",
    "impact": "Use `font-family: 'Bebas Neue', sans-serif`. Ultra-condensed impact headline font. Add `<link href='https://fonts.googleapis.com/css2?family=Bebas+Neue&display=swap' rel='stylesheet'>`.",
    "japanese": "Use `font-family: 'Noto Sans JP', sans-serif`. Clean Japanese-supporting font. Add `<link href='https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;600;700;800;900&display=swap' rel='stylesheet'>`."
}

BUTTONS = {
    "pill": "Rounded pill button: `px-8 py-3 rounded-full font-semibold transition-all duration-300 hover:scale-105 hover:shadow-lg`.",
    "outline": "Ghost/outline button: `px-6 py-3 border-2 border-current bg-transparent font-semibold rounded-lg hover:bg-current hover:text-white transition-all duration-300`.",
    "gradient": "Gradient button: `px-8 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg font-semibold hover:from-purple-700 hover:to-pink-700 shadow-lg hover:shadow-xl transition-all duration-300`.",
    "neon": "Neon glow button: `px-8 py-3 bg-transparent border border-cyan-400 text-cyan-400 rounded-lg font-semibold shadow-[0_0_15px_rgba(6,182,212,0.3)] hover:shadow-[0_0_30px_rgba(6,182,212,0.6)] hover:bg-cyan-400/10 transition-all duration-300`.",
    "brutalist": "Brutalist button: `px-8 py-3 bg-yellow-400 text-black border-4 border-black font-bold uppercase shadow-[4px_4px_0_black] hover:shadow-[2px_2px_0_black] hover:translate-x-[2px] hover:translate-y-[2px] transition-all`.",
    "icon": "Icon button: `p-3 rounded-full bg-white/10 backdrop-blur-sm border border-white/20 hover:bg-white/20 transition-all duration-300` with an SVG icon inside.",
    "magnetic": "Magnetic hover button: `px-8 py-3 bg-black text-white rounded-lg font-semibold relative overflow-hidden group` with a `span` inside using `relative z-10` and a pseudo-element that scales up on hover.",
    "underline": "Underline-reveal button: `px-4 py-2 bg-transparent font-semibold relative after:absolute after:bottom-0 after:left-0 after:w-0 after:h-[2px] after:bg-current after:transition-all after:duration-300 hover:after:w-full`.",
    "3d": "3D press button: `px-8 py-3 bg-blue-500 text-white rounded-lg font-bold border-b-4 border-blue-700 hover:border-b-2 hover:translate-y-[2px] active:border-b-0 active:translate-y-[4px] transition-all`.",
    "glass": "Glass button: `px-8 py-3 bg-white/10 backdrop-blur-md border border-white/20 text-white rounded-xl font-semibold hover:bg-white/20 transition-all duration-300`.",
    "shimmer": "Shimmer button: `px-8 py-3 bg-slate-800 text-white rounded-lg font-semibold relative overflow-hidden` with an animated shimmer pseudo-element sweep.",
    "split": "Split action button: main button on left with `rounded-l-lg` and a dropdown arrow on right with `rounded-r-lg border-l` for multi-action buttons.",
    "floating": "Floating action button (FAB): `fixed bottom-6 right-6 w-14 h-14 rounded-full bg-blue-600 text-white shadow-xl hover:shadow-2xl hover:scale-110 transition-all duration-300 flex items-center justify-center`.",
    "loading": "Loading state button: `px-8 py-3 bg-blue-600 text-white rounded-lg font-semibold inline-flex items-center gap-2 disabled:opacity-50` with a spinning SVG loader icon.",
    "toggle": "Toggle switch button: `relative w-14 h-7 bg-gray-300 rounded-full cursor-pointer` with a sliding circle indicator for on/off states.",
    "social": "Social login button: `px-6 py-3 border border-gray-300 bg-white text-gray-700 rounded-lg font-medium inline-flex items-center gap-3 hover:bg-gray-50 transition-all` with provider icon.",
    "link": "Text link button: `text-blue-600 hover:text-blue-800 underline underline-offset-4 decoration-1 hover:decoration-2 transition-all font-medium`.",
    "chip": "Chip/tag button: `px-4 py-1.5 rounded-full text-sm font-medium bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors cursor-pointer`.",
    "danger": "Danger/destructive button: `px-6 py-3 bg-red-600 text-white rounded-lg font-semibold hover:bg-red-700 shadow-lg shadow-red-500/25 transition-all duration-300`.",
    "success": "Success/confirm button: `px-6 py-3 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700 shadow-lg shadow-emerald-500/25 transition-all duration-300`.",
    "animated-border": "Animated border button: `px-8 py-3 bg-transparent text-white rounded-lg font-semibold relative` with a rotating conic-gradient border animation using pseudo-elements.",
    "text-only": "Text-only minimal button: `px-4 py-2 bg-transparent text-current font-medium hover:opacity-70 transition-opacity` with no border or background."
}

HEROES = {
    "fullscreen-video": "Fullscreen video hero: 100vh container with a `<video autoplay muted loop>` as background, dark overlay, centered headline and CTA. Use `object-cover w-full h-full absolute inset-0`.",
    "gradient-mesh": "Gradient mesh hero: 100vh with multiple overlapping gradient blobs using absolute positioned divs with `rounded-full blur-3xl opacity-30` for a mesh gradient effect behind centered text.",
    "particle": "Particle hero: Dark 100vh background with a canvas or CSS-animated floating dots/particles behind bold centered text and glowing CTA buttons.",
    "split-image": "Split image hero: 50/50 grid. Left side has headline, description, and CTA stack. Right side has a large rounded image or illustration with subtle float animation.",
    "text-only": "Text-only hero: Massive oversized headline (text-7xl+) centered on a clean background with a subtle gradient, thin subheading, and minimal CTA.",
    "carousel-hero": "Carousel hero: Full-width auto-sliding image/content carousel with navigation dots, overlay text, and smooth crossfade transitions.",
    "isometric-cards": "Isometric hero: Centered headline with floating 3D-rotated cards orbiting around it using CSS transforms for an eye-catching tech hero.",
    "animated-bg": "Animated background hero: Moving gradient background using `background-size: 400% 400%; animation: gradientShift 15s ease infinite` with centered content overlay.",
    "scroll-reveal": "Scroll-reveal hero: Content that progressively reveals as user scrolls past the fold using intersection observer triggers.",
    "sticky-hero": "Sticky hero: Hero text stays fixed while background images/sections scroll past, creating a layered depth effect.",
    "blob-hero": "Blob hero: Large organic blob shapes as background decorations with centered content. Use CSS `border-radius: 30% 70% 70% 30% / 30% 30% 70% 70%` animated shapes.",
    "3d-scene": "3D scene hero: CSS 3D transformed elements creating a perspective scene with floating cards/elements at different Z-depths behind the main content.",
    "minimal-hero": "Minimal hero: Single line of large text (text-8xl), extremely generous whitespace, no decorations, and a single subtle link or arrow below.",
    "stats-hero": "Stats hero: Hero section with key metrics/numbers prominently displayed alongside the headline and CTA. Use `text-6xl font-black tabular-nums` for impact.",
    "image-collage": "Image collage hero: Multiple overlapping images at different angles and sizes behind or beside the hero text, creating an editorial look.",
    "countdown-hero": "Countdown hero: Large countdown timer (days:hours:minutes:seconds) as the focal point for product launches or events.",
    "typed-hero": "Typed text hero: Headline with typewriter animation effect, cycling through different words/phrases with a blinking cursor.",
    "wave-hero": "Wave divider hero: Hero section with an SVG wave shape at the bottom edge creating a smooth curved transition to the next section.",
    "diagonal-hero": "Diagonal hero: Content divided diagonally using clip-path, with image on one side and text on the other at an angle.",
    "aurora-hero": "Aurora hero: Dark background with animated aurora borealis-style gradient waves flowing behind centered text content."
}

FOOTERS = {
    "mega-footer": "Large multi-column footer: 4-5 column grid with company info, product links, resources, legal, and newsletter signup. Dark background with subtle top border.",
    "minimal-footer": "Minimal single-line footer: Logo on left, copyright center, social icons on right. Clean `border-t` separator.",
    "wave-footer": "Wave-top footer: SVG wave shape at the top edge of the footer creating a curved transition from the page body into a dark footer section.",
    "cta-footer": "CTA-focused footer: Large call-to-action banner above the footer links section with a bold headline and prominent button.",
    "sticky-footer": "Sticky bottom footer: Thin utility bar fixed at the bottom of the viewport with cookie notice, language selector, or key links.",
    "newsletter-footer": "Newsletter footer: Prominent email signup form as the main footer element, with links below in a secondary row.",
    "social-footer": "Social-media-focused footer: Large social media icons/links as the primary footer content with minimal text links below.",
    "gradient-footer": "Gradient footer: Footer with a gradient background transitioning from the page background color into a darker shade.",
    "centered-footer": "Centered footer: All content centered with logo on top, links in a single row, social icons, and copyright at bottom. Stacked vertical layout.",
    "split-footer": "Split footer: Two-column layout with company info/newsletter on left, and organized link columns on right.",
    "dark-footer": "Dark contrast footer: Very dark (bg-zinc-950) footer regardless of page theme, creating strong visual separation.",
    "branded-footer": "Branded footer: Footer featuring the brand's primary gradient or color prominently, with white text and clear link hierarchy.",
    "accordion-footer": "Accordion footer: Collapsible link sections for mobile-first design, expanding on tap/click to reveal sub-links.",
    "map-footer": "Map footer: Embedded map or location visual alongside contact information and quick links.",
    "app-download-footer": "App download footer: Prominent app store badges (iOS/Android) as the main CTA alongside minimal footer links."
}

SECTIONS = {
    "features-grid": "Feature grid section: 3-column (or 4-column) grid of feature cards, each with an icon/emoji, bold title, and short description. Use consistent card styling with hover lift effect.",
    "testimonials": "Testimonial section: Customer quotes in rounded cards with avatar image, name, role, and star rating. Use a carousel or 3-column grid layout.",
    "pricing-table": "Pricing table: 3-tier pricing cards (Basic/Pro/Enterprise) with a highlighted 'popular' middle card using `scale-105 ring-2 ring-primary`. Each card lists features with checkmarks.",
    "stats-counter": "Stats counter section: 3-4 large animated numbers (e.g., '10K+', '99%', '24/7') with labels below. Use bold typography and `tabular-nums` for clean number display.",
    "faq-accordion": "FAQ accordion section: Expandable question/answer pairs with `+`/`-` toggle icons. Use `details/summary` HTML or JS toggle with smooth height transitions.",
    "cta-banner": "CTA banner section: Full-width gradient or colored banner with a compelling headline and 1-2 action buttons. Use `py-16` padding for visual weight.",
    "team-grid": "Team grid: Cards with team member photos (rounded-full), name, role, and social links. 3-4 column responsive grid.",
    "logo-cloud": "Logo cloud: Row of partner/client logos in grayscale with `opacity-50 hover:opacity-100` transitions. Use `flex flex-wrap justify-center gap-8`.",
    "timeline": "Timeline section: Vertical line with alternating left/right content nodes for company history or process steps. Use `border-l-2` with positioned dot markers.",
    "comparison-table": "Comparison table: Feature comparison grid with checkmarks/crosses across product tiers. Use `table` with sticky header and alternating row colors.",
    "gallery-grid": "Image gallery: Masonry or uniform grid of images with hover overlay showing title/caption. Use `aspect-square object-cover` for consistency.",
    "newsletter-signup": "Newsletter section: Centered heading with email input field and submit button. Use a contrasting background to stand out from other sections.",
    "contact-form": "Contact form section: Name, email, subject, and message fields with a submit button. Use `grid grid-cols-2 gap-4` for side-by-side fields.",
    "process-steps": "Process/how-it-works section: Numbered steps (1-2-3-4) connected by a line or arrows, each with an icon, title, and description.",
    "video-embed": "Video embed section: Centered YouTube/Vimeo embed or custom video player with a play button overlay on a thumbnail. Use `aspect-video rounded-xl overflow-hidden`.",
    "blog-cards": "Blog preview section: 3-column grid of article cards with featured image, category tag, title, excerpt, author avatar, and date.",
    "map-section": "Map section: Embedded Google Maps or interactive map with a side panel containing address, phone, email, and hours of operation.",
    "download-app": "App download section: Split layout with phone mockup on one side and app store download buttons (Apple/Google) with feature bullets on the other.",
    "before-after": "Before/after comparison: Side-by-side or slider comparison showing before and after states, perfect for showcasing transformations.",
    "integrations": "Integrations showcase: Grid of integration/partner logos with connecting lines or a central hub diagram showing connectivity.",
    "social-proof": "Social proof section: Combined testimonials, star ratings, trust badges, and user count metrics in a visually impactful layout.",
    "awards": "Awards/recognition section: Badges, certifications, and award logos displayed in a horizontal scrolling band or grid.",
    "case-studies": "Case study cards: Large cards with client logo, challenge summary, results metrics, and 'Read More' CTA links.",
    "marquee": "Infinite scrolling marquee: Continuously auto-scrolling horizontal band of text, logos, or content using CSS animation.",
    "tabbed-content": "Tabbed content section: Multiple content panels switchable via horizontal tabs, showing different features or categories.",
    "accordion": "Accordion section: Vertically stacked collapsible panels for organizing dense information like specs or details.",
    "parallax-section": "Parallax section: Full-width section with `bg-fixed bg-cover` creating depth as user scrolls past.",
    "breadcrumbs": "Breadcrumb navigation section: Horizontal path showing current page location in site hierarchy.",
    "pagination": "Pagination controls: Numbered page navigation with prev/next buttons, current page highlight, and ellipsis for gaps.",
    "cookie-banner": "Cookie consent banner: Fixed bottom or overlay banner with accept/reject buttons and privacy link.",
    "login-form": "Login form: Email/password fields, remember me checkbox, forgot password link, and social login options.",
    "signup-form": "Signup form: Name, email, password, confirm password with terms checkbox and social signup alternatives."
}

HOVER_EFFECTS = {
    "lift": "Card lift on hover: `hover:-translate-y-2 hover:shadow-xl transition-all duration-300`.",
    "scale": "Scale up on hover: `hover:scale-105 transition-transform duration-300`.",
    "glow": "Glow on hover: `hover:shadow-[0_0_20px_rgba(59,130,246,0.5)] transition-shadow duration-300`.",
    "border-reveal": "Border color reveal: `border-2 border-transparent hover:border-blue-500 transition-colors duration-300`.",
    "bg-shift": "Background color shift: `hover:bg-blue-500 hover:text-white transition-all duration-300`.",
    "tilt": "3D tilt on hover: Use JS to track mouse position and apply `transform: perspective(1000px) rotateX(Xdeg) rotateY(Ydeg)` dynamically.",
    "underline-grow": "Underline grow: `relative after:absolute after:bottom-0 after:left-1/2 after:-translate-x-1/2 after:w-0 after:h-[2px] after:bg-current hover:after:w-full after:transition-all`.",
    "color-fill": "Color fill from bottom: `relative overflow-hidden z-10 before:absolute before:bottom-0 before:left-0 before:w-full before:h-0 before:bg-blue-500 before:-z-10 hover:before:h-full before:transition-all`.",
    "blur-reveal": "Blur to clear on hover: `blur-sm hover:blur-0 transition-all duration-500`.",
    "rotate": "Slight rotate on hover: `hover:rotate-3 transition-transform duration-300`.",
    "grayscale": "Grayscale to color: `grayscale hover:grayscale-0 transition-all duration-500`.",
    "overlay": "Dark overlay on hover: `relative overflow-hidden after:absolute after:inset-0 after:bg-black/0 hover:after:bg-black/40 after:transition-all`.",
    "flip-card": "Flip card on hover: Card flips 180deg on Y-axis revealing back content. Use `perspective-1000` container and `backface-visibility: hidden` on both sides.",
    "slide-text": "Slide-in text on hover: Hidden text slides up from bottom over an image. Use `translate-y-full group-hover:translate-y-0 transition-transform`.",
    "zoom-image": "Image zoom on hover: `overflow-hidden` container with `hover:scale-110 transition-transform duration-500` on the inner image.",
    "shadow-color": "Colored shadow on hover: `hover:shadow-[0_10px_30px_rgba(59,130,246,0.3)] transition-shadow duration-300`.",
    "text-reveal": "Text color reveal: `bg-clip-text text-transparent bg-gradient-to-r from-gray-400 to-gray-400 hover:from-blue-500 hover:to-purple-500 transition-all duration-500`.",
    "skew": "Skew on hover: `hover:skew-x-2 hover:-skew-y-1 transition-transform duration-300`.",
    "brightness": "Brightness change on hover: `hover:brightness-110 transition-all duration-300` for subtle lightening.",
    "ring": "Ring outline on hover: `hover:ring-2 hover:ring-blue-500 hover:ring-offset-2 transition-all duration-300`.",
    "expand": "Expand on hover: `hover:px-10 hover:py-6 transition-all duration-300` for growing padding effect.",
    "morph": "Shape morph on hover: `rounded-lg hover:rounded-full transition-all duration-500` for shape-shifting elements."
}

BACKGROUNDS = {
    "mesh-gradient": "Mesh gradient: Use multiple overlapping `absolute` divs with large `rounded-full blur-3xl opacity-20` gradients for organic mesh backgrounds.",
    "dots": "Dot pattern: `bg-[radial-gradient(circle,_rgba(0,0,0,0.1)_1px,_transparent_1px)] bg-[size:20px_20px]`.",
    "grid-lines": "Grid lines: `bg-[linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[size:40px_40px]`.",
    "diagonal-stripes": "Diagonal stripes: `bg-[repeating-linear-gradient(45deg,transparent,transparent_10px,rgba(255,255,255,0.03)_10px,rgba(255,255,255,0.03)_20px)]`.",
    "noise-texture": "Noise texture: Use a subtle SVG noise filter as a background overlay for organic texture: `url(\"data:image/svg+xml,...\")` with low opacity.",
    "gradient-animated": "Animated gradient: `bg-gradient-to-r from-purple-500 via-pink-500 to-red-500 bg-[length:200%_200%]` with `animation: gradientMove 5s ease infinite`.",
    "waves": "SVG waves: Use an inline or external SVG with wave paths as a section divider or background decoration.",
    "blobs": "Blob shapes: Absolute positioned divs with `border-radius: 30% 70% 70% 30% / 30% 30% 70% 70%` and blur for organic floating shapes.",
    "stars": "Starfield: Dark bg with multiple small `box-shadow` dots to simulate a starry night sky background.",
    "checkerboard": "Checkerboard: `bg-[conic-gradient(at_center,_#0001_25%,_#0000_25%_50%,_#0001_50%_75%,_#0000_75%)] bg-[size:40px_40px]`.",
    "cross-hatch": "Cross-hatch: `bg-[repeating-linear-gradient(0deg,transparent,transparent_9px,rgba(0,0,0,0.03)_9px,rgba(0,0,0,0.03)_10px),repeating-linear-gradient(90deg,transparent,transparent_9px,rgba(0,0,0,0.03)_9px,rgba(0,0,0,0.03)_10px)]`.",
    "radial-gradient": "Radial gradient: `bg-[radial-gradient(ellipse_at_center,_rgba(59,130,246,0.15)_0%,_transparent_70%)]` for a subtle centered glow.",
    "topography": "Topographic lines: CSS background with organic curved repeating line patterns simulating contour map lines.",
    "circuit-board": "Circuit board: Geometric lines and nodes pattern on dark background, perfect for tech/hardware themes.",
    "hexagons": "Hexagon grid: Repeating hexagonal pattern background using CSS clip-path or SVG for tech/blockchain themes.",
    "confetti": "Confetti: Scattered small colored shapes (circles, squares, triangles) using multiple box-shadows for celebration themes.",
    "aurora-bg": "Aurora background: Animated flowing gradient blobs in greens, blues, and purples on a dark canvas.",
    "marble": "Marble texture: Subtle veined marble pattern using layered CSS gradients in whites and grays.",
    "paper": "Paper texture: Subtle off-white background with noise overlay simulating real paper."
}

GRADIENTS = {
    "sunrise": "Use `bg-gradient-to-r from-rose-400 via-amber-300 to-yellow-200` for warm sunrise tones.",
    "ocean": "Use `bg-gradient-to-r from-blue-600 via-cyan-500 to-teal-400` for deep ocean tones.",
    "aurora": "Use `bg-gradient-to-r from-green-400 via-cyan-500 to-blue-500` for northern lights.",
    "sunset": "Use `bg-gradient-to-r from-orange-500 via-rose-500 to-purple-600` for vivid sunset.",
    "neon": "Use `bg-gradient-to-r from-cyan-400 via-fuchsia-500 to-yellow-400` for neon rainbow.",
    "fire": "Use `bg-gradient-to-r from-yellow-400 via-red-500 to-red-700` for fiery blaze.",
    "ice": "Use `bg-gradient-to-r from-blue-200 via-cyan-200 to-white` for frozen ice.",
    "forest": "Use `bg-gradient-to-r from-emerald-700 via-green-600 to-lime-500` for deep forest.",
    "lavender": "Use `bg-gradient-to-r from-purple-400 via-violet-400 to-indigo-400` for soft lavender.",
    "midnight": "Use `bg-gradient-to-r from-slate-900 via-indigo-900 to-purple-900` for deep midnight.",
    "peach": "Use `bg-gradient-to-r from-orange-200 via-rose-200 to-pink-200` for soft peach.",
    "steel": "Use `bg-gradient-to-r from-gray-400 via-slate-500 to-zinc-600` for industrial steel.",
    "candy": "Use `bg-gradient-to-r from-pink-400 via-purple-400 to-indigo-400` for sweet candy.",
    "gold": "Use `bg-gradient-to-r from-yellow-300 via-amber-400 to-orange-500` for metallic gold.",
    "cosmic": "Use `bg-gradient-to-r from-violet-600 via-fuchsia-600 to-pink-600` for cosmic space.",
    "tropical": "Use `bg-gradient-to-r from-emerald-400 via-teal-400 to-cyan-400` for tropical island.",
    "berry": "Use `bg-gradient-to-r from-purple-600 via-pink-600 to-red-500` for mixed berry.",
    "mint": "Use `bg-gradient-to-r from-emerald-300 via-teal-200 to-cyan-200` for fresh mint.",
    "plasma": "Use `bg-gradient-to-r from-fuchsia-600 via-purple-600 to-indigo-600` for plasma energy.",
    "desert": "Use `bg-gradient-to-r from-amber-400 via-orange-400 to-red-400` for desert sand.",
    "rainbow": "Use `bg-gradient-to-r from-red-500 via-yellow-500 via-green-500 via-blue-500 to-purple-500` for full rainbow.",
    "silver": "Use `bg-gradient-to-r from-gray-300 via-white to-gray-300` for metallic silver.",
    "emerald": "Use `bg-gradient-to-r from-emerald-600 via-green-500 to-teal-500` for emerald gem.",
    "rose-gold": "Use `bg-gradient-to-r from-rose-300 via-pink-200 to-amber-200` for rose gold metallic.",
    "electric": "Use `bg-gradient-to-r from-yellow-400 via-lime-400 to-green-400` for electric charge.",
    "abyss": "Use `bg-gradient-to-r from-slate-950 via-blue-950 to-indigo-950` for deep abyss.",
    "sakura": "Use `bg-gradient-to-r from-pink-300 via-rose-200 to-pink-100` for cherry blossom.",
    "holographic": "Use `bg-gradient-to-r from-pink-400 via-blue-400 via-green-400 to-yellow-400` with animation for holographic shimmer."
}

INDUSTRIES = {
    "technology": "Use sleek, modern 'corporate' or 'glassmorphism' styles. Prefer 'blue', 'slate', or 'neon'/'cyberpunk' colors. Fast 'fade' or 'slide' animations.",
    "tech": "Use sleek, modern 'corporate' or 'glassmorphism' styles. Prefer 'blue', 'slate', or 'neon'/'cyberpunk' colors. Fast 'fade' or 'slide' animations.",
    "software": "Use sleek, modern 'corporate' or 'glassmorphism' styles. Prefer 'blue', 'slate', or 'neon'/'cyberpunk' colors. Fast 'fade' or 'slide' animations.",
    "sales": "Use high-conversion 'material' or 'flat' styles. Use high-contrast call-to-action colors like 'red', 'orange', or 'green'. Use 'pulse' or 'bounce' on buy buttons.",
    "ecommerce": "Use clean 'minimalist' or 'corporate' styles. Use 'white' or 'gray' backgrounds to make product images pop, with 'blue' or 'black' text.",
    "e-commerce": "Use clean 'minimalist' or 'corporate' styles. Use 'white' or 'gray' backgrounds to make product images pop, with 'blue' or 'black' text.",
    "restaurant": "Use 'earth', 'sunset', or 'warm' colors like 'orange', 'red', or 'brown'. Use 'classic' serif typography. Large mouth-watering imagery.",
    "food": "Use 'earth', 'sunset', or 'warm' colors like 'orange', 'red', or 'brown'. Use 'classic' serif typography. Large mouth-watering imagery.",
    "portfolio": "Use 'minimalist', 'brutalism', or 'glassmorphism' depending on the creative field. Black and white ('monochrome') with a single vibrant accent color works well.",
    "finance": "Use 'corporate' style with 'navy', 'blue', 'emerald', or 'gold'. Extremely professional, trustworthy, and clean.",
    "crypto": "Use 'dark mode', 'cyber', or 'neon' styles. Colors like 'purple', 'magenta', 'cyan', or 'obsidian'. Use 'glow' effects.",
    "web3": "Use 'dark mode', 'cyber', or 'neon' styles. Colors like 'purple', 'magenta', 'cyan', or 'obsidian'. Use 'glow' effects.",
    "medical": "Use 'flat' or 'corporate' styles. 'White', 'blue', 'teal', or 'cyan' colors. Extremely clean, lots of whitespace, trustworthy.",
    "health": "Use 'flat' or 'corporate' styles. 'White', 'blue', 'teal', or 'cyan' colors. Extremely clean, lots of whitespace, trustworthy.",
    "hospital": "Use 'flat' or 'corporate' styles. 'White', 'blue', 'teal', or 'cyan' colors. Extremely clean, lots of whitespace, trustworthy.",
    "clinic": "Use 'flat' or 'corporate' styles. 'White', 'blue', 'teal', or 'cyan' colors. Extremely clean, lots of whitespace, trustworthy.",
    "fitness": "Use 'brutalism' or high-contrast 'dark mode'. 'Black', 'red', 'neon yellow'. Aggressive, energetic fonts and angles.",
    "gym": "Use 'brutalism' or high-contrast 'dark mode'. 'Black', 'red', 'neon yellow'. Aggressive, energetic fonts and angles.",
    "education": "Use 'flat', 'material', or 'friendly' styles. 'Blue', 'green', 'yellow'. Legible sans-serif fonts, structured card layouts.",
    "school": "Use 'flat', 'material', or 'friendly' styles. 'Blue', 'green', 'yellow'. Legible sans-serif fonts, structured card layouts.",
    "real estate": "Use 'luxury' or 'corporate' styles. 'White', 'navy', 'gold', or 'slate'. Elegant fonts, large image galleries.",
    "gaming": "Use 'dark mode', 'cyberpunk', or 'brutalism' styles. Intense neon or fiery contrasting colors (like electric blue, crimson red, dark obsidian). Glows, hover card scales, dynamic action fonts.",
    "game": "Use 'dark mode', 'cyberpunk', or 'brutalism' styles. Intense neon or fiery contrasting colors (like electric blue, crimson red, dark obsidian). Glows, hover card scales, dynamic action fonts.",
    "agency": "Use sleek 'minimalist', 'brutalism', or 'glassmorphism' styles. Use striking, creative accent colors like 'orange' or 'neon', with large bold headlines.",
    "design": "Use ultra-modern 'minimalist' or 'asymmetric-mesh' layouts. Focus on typography, layout space, and high-quality visuals. Accentuate with 'monochrome' or 'luxury' palettes.",
    "fashion": "Use high-end 'luxury' or 'minimalist' styles. Use elegant serif fonts, extremely large fullscreen hero sections, minimal borders, and a 'pearl' or 'ivory' background theme.",
    "law": "Use classic 'corporate' or 'gothic' styles. Slate, navy, or deep maroon colors. Serif headers, structured high-trust layout, minimal animations.",
    "consulting": "Use professional 'corporate' style. Dark navy/slate and silver colors. Clean typography, trust metrics, client logos, and structured info cards.",
    "architecture": "Use 'minimalist', 'nordic', or 'wireframe' styles. Large structural photos, thin grid borders, high whitespace, and sophisticated sans-serif fonts.",
    "travel": "Use warm 'sunset', 'ocean', or 'earth' colors. Highly visual with large postcard-style gallery cards, floating badges, and smooth scroll animations.",
    "music": "Use 'dark mode', 'synthwave', or 'cyberpunk' colors. High-contrast gradients, soundwave visualizer motifs, large call-to-actions, and glowing buttons.",
    "beauty": "Use elegant 'sakura', 'lavender', or 'peach' color themes. Soft claymorphism, rounded friendly card shapes, and delicate animations.",
    "sports": "Use high-energy 'volcanic' or 'neon' styles. Large slanted text, aggressive brutalist borders, intense action shots, and fast slide animations.",
    "automotive": "Use dark 'carbon' or 'obsidian' metallic styles. Deep contrast, glowing headlights/accents, sharp corners, and high-tech typography.",
    "agriculture": "Use natural 'earth' or 'forest' green themes. Warm stone backgrounds, rounded corners, organic illustrations, and clean legible structures.",
    "nonprofit": "Use warm, friendly 'emerald' or 'earth' color palettes. Heartwarming imagery, prominent donate call-to-actions, and clean, legible info cards.",
    "blog": "Use highly legible 'minimalist' or 'nordic' typography. Large readable text blocks, generous line-heights, subtle headers, and clean tag filters.",
    "saas": "Use 'glassmorphism' or modern 'corporate' styles. Purple/blue gradients, clean feature grids, prominent pricing tables, and trust badges.",
    "startup": "Use bold, energetic 'gradient' styles. Large hero sections, social proof counters, feature showcases, and prominent CTA buttons.",
    "wedding": "Use 'elegant' or 'sakura' themes. Soft pastels, serif fonts, large photo galleries, RSVP forms, and timeline countdown.",
    "photography": "Use 'minimalist' dark or light themes. Let images dominate with full-bleed galleries, masonry grids, and subtle hover overlays.",
    "podcast": "Use 'dark mode' or 'synthwave' styles. Audio player UI, episode cards, guest profiles, and bold typography.",
    "event": "Use vibrant, attention-grabbing styles. Countdown timers, speaker grids, agenda timelines, and ticket CTA buttons.",
    "insurance": "Use trustworthy 'corporate' style. Blue/teal tones, clean comparison tables, testimonials, and trust badges.",
    "logistics": "Use professional 'corporate' style. Tracking UI elements, map integrations, service grids, and navy/orange accents.",
    "pet": "Use playful 'kawaii' or warm 'earth' themes. Rounded cards, paw-print motifs, warm colors, and friendly sans-serif fonts.",
    "kids": "Use bright, colorful 'candy' or 'bubblegum' themes. Large rounded elements, playful animations, and oversized friendly typography.",
    "news": "Use structured 'corporate' magazine layouts. Multi-column grids, category tags, author bylines, and clear reading hierarchy.",
    "church": "Use warm, welcoming 'earth' or 'ivory' themes. Serif fonts, event calendars, sermon archives, and donation CTAs.",
    "bakery": "Use warm 'peach', 'cream', or 'coffee' themes. Script/handwritten fonts, menu cards, large food photography, and order buttons.",
    "construction": "Use rugged 'steel' or 'charcoal' themes. Bold sans-serif fonts, project galleries, service grids, and safety-yellow accents.",
    "government": "Use accessible 'corporate' or 'navy' themes. High-contrast text, structured navigation, clear information hierarchy, and WCAG compliance.",
    "ai": "Use futuristic 'neon' or 'cyber' dark themes. Gradient mesh backgrounds, animated particles, neural network motifs, and glowing accents.",
    "marketing": "Use high-energy gradient styles. Conversion-focused layouts, A/B metrics displays, bold CTAs, and social proof sections.",
    "dentist": "Use clean 'corporate' or 'flat' styles. Light blue/teal and white. Friendly rounded cards, smile imagery, and appointment booking CTAs.",
    "spa": "Use 'sakura', 'lavender', or 'peach' soft themes. Serif fonts, gentle animations, large relaxation imagery, and booking forms.",
    "cafe": "Use warm 'coffee', 'cream', or 'earth' themes. Handwritten/script fonts, menu displays, cozy imagery, and order-online CTAs.",
    "freelancer": "Use 'minimalist' or 'brutalism' personal brand styles. Bold name header, project showcase grid, skills section, and contact form.",
    "streaming": "Use dark 'obsidian' or 'neon' themes. Card-heavy content grids, play buttons, episode lists, and bold thumbnail imagery.",
    "museum": "Use 'art-deco', 'gothic', or 'minimalist' styles. Serif fonts, exhibition galleries, event calendars, and elegant navigation.",
    "library": "Use 'light-academia' or 'nordic' themes. Warm cream backgrounds, serif fonts, search-centric layouts, and card catalogs.",
    "pharmacy": "Use clean 'corporate' or 'flat' styles. Green/white/teal colors. Product grids, health info cards, and prescription upload CTAs.",
    "veterinary": "Use warm 'earth' or 'mint' themes. Friendly rounded elements, pet-friendly imagery, appointment booking, and service cards.",
    "cleaning": "Use fresh 'aqua', 'mint', or 'blue' themes. Clean layouts, before/after galleries, service pricing tables, and booking forms.",
    "tutoring": "Use friendly 'material' or 'flat' styles. Bright primary colors, subject cards, tutor profiles, scheduling tools.",
    "yoga": "Use serene 'pastel', 'sage', or 'lavender' themes. Organic shapes, breathing-space layouts, class schedules, and mindful typography.",
    "coworking": "Use modern 'glassmorphism' or 'corporate' styles. Space photos, membership cards, amenity grids, and tour booking CTAs.",
    "charity": "Use warm 'earth' or 'emerald' themes. Impact counters, donation progress bars, story cards, and prominent give-now buttons.",
    "hosting": "Use tech 'cyber' or 'corporate' styles. Server specs tables, uptime counters, pricing comparisons, and trust badges.",
    "dating": "Use warm 'rose', 'sakura', or 'candy' themes. Profile cards, match percentages, swipe-style interactions, and heart motifs.",
    "astrology": "Use mystical 'midnight', 'galaxy', or 'amethyst' themes. Star charts, zodiac icons, celestial patterns, and serif fonts.",
    "crypto-exchange": "Use dark 'obsidian' or 'cyber' themes. Live price tickers, candlestick chart motifs, trading UI elements, and green/red indicators."
}

MOODS = {
    "happy": "Use bright, warm, and playful colors (yellows, pinks, light blues). Add bouncy animations and rounded, friendly UI elements.",
    "dark": "Use a deep dark mode (zinc-950 or black). Use subtle glowing effects and minimalist typography.",
    "scary": "Use high contrast red and black. Add flickering animations or harsh brutalist borders.",
    "professional": "Use corporate blues, slate grays, and white. Very clean layout, structured cards, readable sans-serif typography.",
    "elegant": "Use monochrome or luxury gold/black. Thin, elegant serif fonts. Lots of whitespace. Very slow, smooth fade animations.",
    "playful": "Use the candy or kawaii theme. Rounded shapes, large friendly text, and springy hover effects.",
    "futuristic": "Use cyberpunk, neon, or holographic elements. Glow effects, dark backgrounds, monospaced or geometric fonts.",
    "retro": "Use vaporwave, retro-futurism, or 80s styles. CRT effects, bright cyan/magenta, or earthy 70s tones.",
    "minimal": "Use extreme whitespace, monochrome or neutral colors. Barely visible borders, no heavy shadows.",
    "cozy": "Use soft warm colors (peach, brown, ivory), gentle rounded corners, subtle shadows, and friendly serif typography.",
    "aggressive": "Use high contrast colors (red, black, neon yellow), sharp edges, slanted sections, thick borders, and heavy bold uppercase fonts.",
    "calm": "Use muted blue-green tones (turquoise, jade, pastel), plenty of whitespace, slow fade animations, and thin modern fonts.",
    "mysterious": "Use midnight or obsidian colors, heavy dark blur overlays, glowing neon details, and floating animations.",
    "energetic": "Use volcanic or candy colors, fast springy animations, floating bubbles, and bold gradients.",
    "nostalgic": "Use retro or vaporwave palettes, pixelated details, classic serif or typewriter fonts, and grainy background textures.",
    "clean": "Use minimalist gray or white themes, perfect margins, thin borders, clear hierarchy, and no visual clutter.",
    "trustworthy": "Use navy or cobalt corporate schemes, solid borders, structured table grids, and clear sans-serif typography.",
    "romantic": "Use soft rose/pink tones, flowing serif fonts, gentle gradients, subtle blur effects, and delicate heart or floral motifs.",
    "luxurious": "Use gold/amber accents on deep black, thin elegant fonts, generous spacing, and subtle shimmer animations.",
    "techy": "Use monospace fonts, dark backgrounds, terminal-green or cyan accents, grid overlays, and code-block inspired layouts.",
    "whimsical": "Use irregular shapes, hand-drawn borders, pastel colors, bouncy animations, and playful mixed typography.",
    "corporate": "Use structured blue/gray schemes, clean grid layouts, standard shadows, professional sans-serif fonts, and subtle transitions.",
    "rebellious": "Use clashing neon colors on black, grunge textures, irregular layouts, glitch effects, and heavy distorted fonts.",
    "serene": "Use muted ocean blues and greens, lots of breathing room, gentle wave patterns, and ultra-slow fade animations.",
    "bold": "Use oversized typography, high-contrast color pairs, thick borders, heavy font weights, and dramatic entrance animations.",
    "dreamy": "Use soft pastels with heavy blur overlays, floating elements, gradient mesh backgrounds, and slow ethereal animations.",
    "industrial": "Use raw concrete grays, exposed-grid layouts, monospace fonts, sharp edges, and minimal decoration.",
    "zen": "Use extreme emptiness, stone/beige backgrounds, single accent color, and one piece of content at a time with breathing room.",
    "chaotic": "Use clashing colors, overlapping elements, rotated text, asymmetric grids, and rapid multi-directional animations.",
    "warm": "Use amber, orange, and yellow tones. Soft glows, rounded corners, warm shadows, and inviting serif fonts.",
    "cool": "Use blue, cyan, and slate tones. Sharp edges, cool shadows, thin sans-serif fonts, and subtle animations.",
    "sophisticated": "Use muted jewel tones, thin typography, generous negative space, and micro-interactions only.",
    "raw": "Use unpolished elements, monospace fonts, visible grid lines, minimal color, and functional-first layout.",
    "haunted": "Use deep blacks and purples, flickering text, eerie gradients, distorted fonts, and unsettling animations.",
    "powerful": "Use bold blacks with vibrant accents, ultra-heavy font weights, large scale elements, and impactful entrance animations.",
    "gentle": "Use the softest pastels possible, thin delicate lines, light font weights, and barely-visible transitions.",
    "vibrant": "Use highly saturated colors from multiple hues, bold contrasts, animated gradients, and lively hover effects.",
    "subdued": "Use desaturated muted tones, low contrast, gentle borders, and restrained decoration.",
    "artsy": "Use creative asymmetric layouts, mixed fonts, splatter effects, hand-drawn elements, and artistic color choices.",
    "scientific": "Use data-visualization inspired layouts, monospace fonts, chart elements, grid backgrounds, and clinical blue/gray tones.",
    "magical": "Use deep purples and golds, sparkle/star particle effects, glowing elements, and enchanting gradient backgrounds.",
    "vintage": "Use sepia tones, aged paper textures, ornamental borders, classic serif fonts, and film-grain overlays."
}

LAYOUTS = {
    "split-screen": "Use a split-screen layout for the hero section: text and primary call-to-actions on one side (left or right), and a prominent visual card, product showcase, mockup, or interactive grid on the other side.",
    "centered-hero": "Use a centered stacked hero layout: a massive, bold main headline in the center of the viewport, with subheadings, stacked CTA buttons, and a grid of floating card items directly below it.",
    "asymmetric-mesh": "Use an asymmetric, modern design: text shifted off-center with staggered cards, overlapping borders, and abstract gradient circles floating behind sections to create a layer of depth.",
    "dashboard-grid": "Use a dashboard or card-centric layout: structure the entire page around a clean, multi-column grid system with visible borders, unified cards, and separate metric blocks rather than standard text sections.",
    "minimal-whitespace": "Use a minimal design layout: maximize whitespace, utilize oversized headlines with high letter-spacing, and place clean simple two-column descriptions with absolute minimal graphical noise.",
    "diagonal-split": "Use a diagonal split screen: use CSS clip-path or angled borders to create diagonal section dividers that break the page visually between the header and the body sections.",
    "bento-grid": "Use a trendy Bento box grid layout: structure the section using CSS grid with varying row/col spans to create a mosaic of modular, rounded info cards with subtle hover scaling.",
    "zigzag-timeline": "Use a alternating zigzag timeline layout: content alternates left and right of a central line, making it perfect for storytelling, history, or step-by-step features.",
    "fullscreen-scroll": "Use a fullscreen section scroll layout: each section occupies exactly 100vh with centered content, designed to be navigated sequentially.",
    "horizontal-carousel": "Use a horizontal scrolling layout: content sections or cards are aligned horizontally, allowing users to swipe or scroll sideways instead of vertically.",
    "sidebar-content": "Use a two-column sidebar layout: a fixed navigation/filter sidebar on the left taking up 25% of the screen, and a main scrollable content grid taking up 75%.",
    "stacked-cards": "Use a overlapping stacked cards layout: cards or sections appear to stack on top of each other as the user scrolls, creating a beautiful parallax scrolling depth effect.",
    "masonry": "Use a masonry grid layout: items are arranged in multiple columns with varying heights, optimized for portfolios, image galleries, or creative blogs.",
    "magazine": "Use a magazine-style multi-column layout: featured article large at top, smaller articles in 2-3 columns below, with category sidebars and pull quotes.",
    "landing-page": "Use a conversion-focused single-column layout: hero → social proof → features → testimonials → pricing → CTA → footer. Optimized for scroll conversion.",
    "app-showcase": "Use a product showcase layout: centered phone/laptop mockup with feature callouts pointing to it, surrounded by gradient backgrounds and floating UI elements.",
    "one-page": "Use a smooth single-page scroll layout: all content on one page with section anchors, smooth scroll behavior, and a fixed nav with section indicators.",
    "grid-gallery": "Use a uniform grid gallery: equal-sized cards in a responsive CSS grid with hover overlay effects for portfolios and image-heavy sites.",
    "f-pattern": "Use an F-pattern reading layout: important content along the top and left, supporting content on the right, following natural eye-scanning patterns.",
    "hero-cards": "Use a hero-with-cards layout: large hero section followed immediately by 3-4 feature cards that overlap the hero bottom edge using negative margin-top."
}

NAV_STYLES = {
    "floating-pill": "Use a transparent floating navigation bar: centered on the page with rounded-full corners, backdrop-blur effect, and a thin border to make it hover over the content.",
    "sticky-full": "Use a classic sticky full-width navigation bar: solid background color matching the page's theme, and a thin glowing border at the bottom that remains fixed at the top of the screen.",
    "sidebar-dock": "Use a vertical dock navigation layout: place a sleek, narrow navbar fixed on the left side of the viewport, with round icon buttons that slide open on hover.",
    "minimal-logo": "Use a clean header navigation: logo aligned to the left, central menu links hidden on mobile but showing as standard pill buttons on desktop, and a single prominent call-to-action button on the far right.",
    "hidden-hamburger": "Use a clean, hidden hamburger navigation: only show a small floating menu icon at the top corner, which triggers a beautiful fullscreen animated navigation overlay on click.",
    "bottom-dock": "Use a mobile-friendly bottom dock navigation bar: fixed at the bottom center of the viewport, styled like an iOS dock with pill-shaped active states and smooth bounce hover animations.",
    "glassy-header": "Use a top header navigation with a frosted-glass backdrop: stretches full-width with a subtle border-b, blurring whatever content slides underneath it as the user scrolls.",
    "double-decker": "Use a dual-level header: a top utility bar with secondary links, announcements, or language selectors, and a main bottom navigation bar with primary links and the logo.",
    "circular-menu": "Use a radial circular menu: a floating action button in the bottom-right corner that expands into a ring of menu shortcuts when clicked or hovered.",
    "breadcrumb-nav": "Use breadcrumb navigation: a horizontal path trail showing the user's location in the site hierarchy (Home > Category > Page) with clickable links.",
    "tab-nav": "Use tab-style navigation: horizontal tabs at the top of content sections with active tab indicator, underline or filled style, and smooth content switching.",
    "mega-menu": "Use a mega dropdown menu: hovering over nav items reveals a large multi-column dropdown with categorized links, images, and featured content.",
    "progress-nav": "Use a progress-bar navigation: a thin horizontal bar at the very top showing scroll progress or step completion percentage.",
    "animated-underline": "Use animated underline navigation: clean text links where a colored underline slides in from left on hover with smooth CSS transitions."
}

def scan_query_for_elements(query: str) -> str:
    """Scans the user query for keywords matching colors, animations, styles, effects, and moods, returning a compiled directive."""
    query_lower = query.lower()
    directives = []
    
    # Check for layouts
    matched_layouts = []
    for layout_name, description in LAYOUTS.items():
        if layout_name in query_lower:
            matched_layouts.append(f"Layout '{layout_name}': {description}")
            
    if not matched_layouts:
        import random
        random_layout = random.choice(list(LAYOUTS.keys()))
        matched_layouts.append(f"Layout '{random_layout}' (Randomly Selected for variety): {LAYOUTS[random_layout]}")
        
    if matched_layouts:
        directives.append("=== DESIGN LAYOUT & WIREFRAME ===")
        directives.extend(matched_layouts)

    # Check for nav styles
    matched_navs = []
    for nav_name, description in NAV_STYLES.items():
        if nav_name in query_lower:
            matched_navs.append(f"Navigation '{nav_name}': {description}")
            
    if not matched_navs:
        import random
        random_nav = random.choice(list(NAV_STYLES.keys()))
        matched_navs.append(f"Navigation '{random_nav}' (Randomly Selected for variety): {NAV_STYLES[random_nav]}")
        
    if matched_navs:
        directives.append("=== NAVIGATION STYLE ===")
        directives.extend(matched_navs)
    
    # Check for negations
    negation_words = ["no ", "without ", "don't ", "dont ", "avoid ", "remove ", "not "]
    if any(word in query_lower for word in negation_words):
        directives.append("=== NEGATIVE CONSTRAINTS ===")
        directives.append("CRITICAL: The user explicitly used negative constraints ('no', 'without', 'don't', etc.). You MUST carefully read the prompt and absolutely AVOID adding whatever elements they asked to omit.")
        
    # Check for "Wow me" instructions
    wow_words = ["beautiful", "awesome", "stunning", "wow", "amazing", "best", "incredible", "gorgeous", "smart", "attractive", "modern", "premium"]
    if any(word in query_lower for word in wow_words):
        directives.append("=== CREATIVE FREEDOM ===")
        directives.append("The user has asked for a visually stunning, top-tier result. You have full creative freedom to utilize the most advanced, premium Tailwind CSS techniques, complex micro-animations, and striking layouts to WOW the user.")
    
    # Check for colors
    matched_colors = []
    for color_name, description in COLORS.items():
        if color_name in query_lower:
            matched_colors.append(f"Theme '{color_name}': {description}")
            
    # Extract hex codes dynamically
    hex_colors = re.findall(r'#(?:[0-9a-fA-F]{3}){1,2}\b', query)
    if hex_colors:
        matched_colors.append(f"Requested exact Hex Colors: {', '.join(hex_colors)}. You MUST use these exact colors using Tailwind arbitrary values (e.g., bg-[{hex_colors[0]}] or text-[{hex_colors[0]}]).")
        
    # Catch-all rule for custom/unrecognized colors
    if "color" in query_lower or "theme" in query_lower or "palette" in query_lower or matched_colors or hex_colors:
        matched_colors.append("Dynamic Colors: If the user requested a specific color by name (e.g., 'chartreuse', 'mint', 'periwinkle') that is not explicitly defined above, you MUST intelligently infer its hex code and use it via Tailwind arbitrary values (e.g., bg-[#xxx]).")

    # If no colors or hex colors matched, select a random theme to inject variety
    if not matched_colors and not hex_colors:
        import random
        random_color = random.choice(list(COLORS.keys()))
        matched_colors.append(f"Theme '{random_color}' (Randomly Selected for variety): {COLORS[random_color]}")

    if matched_colors:
        directives.append("=== REQUESTED COLORS & THEMES ===")
        directives.extend(matched_colors)
        
    # Check for animations
    matched_animations = []
    for anim_name, css_code in ANIMATIONS.items():
        if anim_name in query_lower:
            matched_animations.append(f"Animation '{anim_name}':\n{css_code}")
            
    if "animation" in query_lower or "animate" in query_lower or not matched_animations:
        if not matched_animations:
            import random
            random_anims = random.sample(list(ANIMATIONS.keys()), 2)
            for anim in random_anims:
                matched_animations.append(f"Animation '{anim}' (Randomly Selected for variety):\n{ANIMATIONS[anim]}")
            
    if matched_animations:
        directives.append("=== REQUESTED ANIMATIONS ===")
        directives.extend(matched_animations)
        
    # Check for styles
    matched_styles = []
    for style_name, rules in STYLES.items():
        if style_name in query_lower:
            matched_styles.append(f"Style '{style_name}': {rules}")
            
    if not matched_styles:
        import random
        random_style = random.choice(list(STYLES.keys()))
        matched_styles.append(f"Style '{random_style}' (Randomly Selected for variety): {STYLES[random_style]}")
            
    if matched_styles:
        directives.append("=== REQUESTED DESIGN STYLES ===")
        directives.extend(matched_styles)
        
    # Check for effects
    matched_effects = []
    for effect_name, rules in EFFECTS.items():
        if effect_name in query_lower:
            matched_effects.append(f"Effect '{effect_name}': {rules}")
            
    if matched_effects:
        directives.append("=== REQUESTED EFFECTS ===")
        directives.extend(matched_effects)

    # Check for typography
    matched_typo = []
    for typo_name, rules in TYPOGRAPHY.items():
        if re.search(r'\b' + re.escape(typo_name) + r'\b', query_lower):
            matched_typo.append(f"Typography '{typo_name}': {rules}")
    if "font" in query_lower or "typography" in query_lower:
        if not matched_typo:
            import random
            rand_typo = random.choice(list(TYPOGRAPHY.keys()))
            matched_typo.append(f"Typography '{rand_typo}' (Randomly Selected): {TYPOGRAPHY[rand_typo]}")
    if matched_typo:
        directives.append("=== TYPOGRAPHY ===")
        directives.extend(matched_typo)

    # Check for button styles
    matched_buttons = []
    for btn_name, rules in BUTTONS.items():
        if btn_name + " button" in query_lower or btn_name + " btn" in query_lower:
            matched_buttons.append(f"Button '{btn_name}': {rules}")
    if "button" in query_lower or "btn" in query_lower or "cta" in query_lower:
        if not matched_buttons:
            import random
            rand_btn = random.choice(list(BUTTONS.keys()))
            matched_buttons.append(f"Button '{rand_btn}' (Randomly Selected): {BUTTONS[rand_btn]}")
    if matched_buttons:
        directives.append("=== BUTTON STYLES ===")
        directives.extend(matched_buttons)

    # Check for hero styles
    matched_heroes = []
    for hero_name, rules in HEROES.items():
        if hero_name in query_lower:
            matched_heroes.append(f"Hero '{hero_name}': {rules}")
    if "hero" in query_lower or "landing" in query_lower or "header" in query_lower:
        if not matched_heroes:
            import random
            rand_hero = random.choice(list(HEROES.keys()))
            matched_heroes.append(f"Hero '{rand_hero}' (Randomly Selected): {HEROES[rand_hero]}")
    if matched_heroes:
        directives.append("=== HERO SECTION STYLE ===")
        directives.extend(matched_heroes)

    # Check for footer styles
    matched_footers = []
    for footer_name, rules in FOOTERS.items():
        if footer_name in query_lower:
            matched_footers.append(f"Footer '{footer_name}': {rules}")
    if "footer" in query_lower:
        if not matched_footers:
            import random
            rand_footer = random.choice(list(FOOTERS.keys()))
            matched_footers.append(f"Footer '{rand_footer}' (Randomly Selected): {FOOTERS[rand_footer]}")
    if matched_footers:
        directives.append("=== FOOTER STYLE ===")
        directives.extend(matched_footers)

    # Check for section types
    matched_sections = []
    for sec_name, rules in SECTIONS.items():
        if sec_name in query_lower:
            matched_sections.append(f"Section '{sec_name}': {rules}")
    section_keywords = ["pricing", "testimonial", "faq", "feature", "team", "contact", "blog", "gallery", "timeline", "stats", "newsletter"]
    for kw in section_keywords:
        if kw in query_lower:
            for sec_name, rules in SECTIONS.items():
                if kw in sec_name and f"Section '{sec_name}'" not in str(matched_sections):
                    matched_sections.append(f"Section '{sec_name}': {rules}")
    if matched_sections:
        directives.append("=== SECTION COMPONENTS ===")
        directives.extend(matched_sections)

    # Check for hover effects
    matched_hovers = []
    for hover_name, rules in HOVER_EFFECTS.items():
        if hover_name in query_lower and "hover" in query_lower:
            matched_hovers.append(f"Hover Effect '{hover_name}': {rules}")
    if matched_hovers:
        directives.append("=== HOVER EFFECTS ===")
        directives.extend(matched_hovers)

    # Check for background patterns
    matched_bgs = []
    for bg_name, rules in BACKGROUNDS.items():
        if bg_name in query_lower:
            matched_bgs.append(f"Background '{bg_name}': {rules}")
    if "background" in query_lower or "bg" in query_lower or "pattern" in query_lower:
        if not matched_bgs:
            import random
            rand_bg = random.choice(list(BACKGROUNDS.keys()))
            matched_bgs.append(f"Background '{rand_bg}' (Randomly Selected): {BACKGROUNDS[rand_bg]}")
    if matched_bgs:
        directives.append("=== BACKGROUND PATTERNS ===")
        directives.extend(matched_bgs)

    # Check for gradients
    matched_grads = []
    for grad_name, rules in GRADIENTS.items():
        if grad_name + " gradient" in query_lower:
            matched_grads.append(f"Gradient '{grad_name}': {rules}")
    if "gradient" in query_lower:
        if not matched_grads:
            import random
            rand_grad = random.choice(list(GRADIENTS.keys()))
            matched_grads.append(f"Gradient '{rand_grad}' (Randomly Selected): {GRADIENTS[rand_grad]}")
    if matched_grads:
        directives.append("=== GRADIENT PRESETS ===")
        directives.extend(matched_grads)
        
    # Check for moods
    matched_moods = []
    for mood_name, rules in MOODS.items():
        if re.search(r'\b' + re.escape(mood_name) + r'\b', query_lower):
            matched_moods.append(f"Mood '{mood_name}': {rules}")
            
    if matched_moods:
        directives.append("=== MOOD & VIBE ADAPTATION ===")
        directives.extend(matched_moods)
        
    # Check for industry/domain
    matched_industries = []
    for industry_name, rules in INDUSTRIES.items():
        # Use word boundaries for shorter industry names to avoid false positives
        if re.search(r'\b' + re.escape(industry_name) + r'\b', query_lower):
            matched_industries.append(f"Industry '{industry_name}': {rules}")
            
    if matched_industries:
        directives.append("=== INDUSTRY & DOMAIN ADAPTATION ===")
        directives.extend(matched_industries)
        directives.append("CRITICAL OVERRIDE: If the user explicitly requested specific colors, animations, effects, or styles (listed above), those specific choices MUST OVERRIDE any conflicting industry defaults. Only use the industry defaults to fill in the gaps for elements the user did not explicitly specify.")
    elif "for" in query_lower or "website" in query_lower or "page" in query_lower:
        # Generic fallback
        directives.append("=== INDUSTRY & DOMAIN ADAPTATION ===")
        directives.append("If the user mentions a specific industry or purpose (e.g. sales, blog, agency), you MUST automatically select the highest-converting, most professional color palette, typography, and layout style tailored perfectly for that industry.")
        directives.append("CRITICAL OVERRIDE: If the user explicitly requested specific colors, animations, effects, or styles (listed above), those specific choices MUST OVERRIDE any conflicting industry defaults. Only use the industry defaults to fill in the gaps for elements the user did not explicitly specify.")

    if directives:
        return "\\n\\n[ELEMENTS DATABASE DIRECTIVES (MANDATORY)]\\n" + "\\n".join(directives) + "\\n"
    
    return ""
