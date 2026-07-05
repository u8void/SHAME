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
    "brown": "Primary: amber-800, Secondary: amber-700, Background: amber-50, Text: amber-950. Classic basic brown."
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
.animate-zoom-in-down { animation: zoomInDown 1s; }"""
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
    "psychedelic": "Trippy, swirling patterns, extremely saturated clashing colors, distorted typography. Use intense gradients and warped shapes."
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
    "glass": "Use `bg-white/10 backdrop-blur-lg border border-white/20` for a glass effect."
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
    "fitness": "Use 'brutalism' or high-contrast 'dark mode'. 'Black', 'red', 'neon yellow'. Aggressive, energetic fonts and angles.",
    "gym": "Use 'brutalism' or high-contrast 'dark mode'. 'Black', 'red', 'neon yellow'. Aggressive, energetic fonts and angles.",
    "education": "Use 'flat', 'material', or 'friendly' styles. 'Blue', 'green', 'yellow'. Legible sans-serif fonts, structured card layouts.",
    "school": "Use 'flat', 'material', or 'friendly' styles. 'Blue', 'green', 'yellow'. Legible sans-serif fonts, structured card layouts.",
    "real estate": "Use 'luxury' or 'corporate' styles. 'White', 'navy', 'gold', or 'slate'. Elegant fonts, large image galleries."
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
    "minimal": "Use extreme whitespace, monochrome or neutral colors. Barely visible borders, no heavy shadows."
}

def scan_query_for_elements(query: str) -> str:
    """Scans the user query for keywords matching colors, animations, styles, effects, and moods, returning a compiled directive."""
    query_lower = query.lower()
    directives = []
    
    # Check for negations
    negation_words = ["no ", "without ", "don't ", "dont ", "avoid ", "remove ", "not "]
    if any(word in query_lower for word in negation_words):
        directives.append("=== NEGATIVE CONSTRAINTS ===")
        directives.append("CRITICAL: The user explicitly used negative constraints ('no', 'without', 'don't', etc.). You MUST carefully read the prompt and absolutely AVOID adding whatever elements they asked to omit.")
        
    # Check for "Wow me" instructions
    wow_words = ["beautiful", "awesome", "stunning", "wow", "amazing", "best", "incredible", "gorgeous", "smart"]
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
