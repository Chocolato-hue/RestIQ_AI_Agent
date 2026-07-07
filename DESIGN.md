# RestIQ Design System Spec (open-design.ai)

This design system spec acts as the brand contract for RestIQ. Coding agents and linting rules must adhere to these tokens and visual guidelines.

---

## 🎨 Visual Identity & Color Tokens

RestIQ utilizes a modern, dark-mode-first HSL color palette tailored for sleep health, circadian biology, and premium agent interfaces.

### Brand Core
- **Background (Deep Space):** `#0a0e1a` (hsl(225, 45%, 7%))
- **Elevated Surfaces:** `#0f172a` (hsl(222, 47%, 11%))
- **Glass Panel Fill:** `rgba(15, 23, 42, 0.8)` with `backdrop-filter: blur(16px)`

### Primary Accents (Circadian Cycles)
- **Indigo (Melatonin / Night):** `#6366f1` (hsl(239, 84%, 66%))
- **Emerald (Cortisol / Wakefulness):** `#10b981` (hsl(162, 76%, 45%))
- **Amber (Wind-down Alert):** `#f59e0b` (hsl(38, 92%, 50%))
- **Coral (Sleep Interruption):** `#ef4444` (hsl(0, 84%, 60%))

---

## 📐 Layout & Card Standards (Craft)

1. **Borders:** Every surface must utilize a thin, translucent border of `rgba(148, 163, 184, 0.1)`. No solid, stark borders.
2. **Radius:** High-radius styling:
   - Compact elements (inputs, tooltips): `10px`
   - Primary elements (cards, headers): `16px`
   - Layout panels (sidebars, forms): `24px`
3. **Shadows:** Avoid drop-shadow offsets. Use diffuse blur shadows combined with subtle inner glows:
   - `box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.05)`
4. **Spacing:** Standard modular scale based on `8px` steps: `8px`, `16px`, `24px`, `32px`, `48px`.

---

## 🔄 Animations & Transitions

1. **Spring Motion:** All standard hovers must transition over `200ms ease` for standard elements. High-emphasis elements (cards, buttons) should scale slightly: `transform: scale(1.02) translateY(-2px)`.
2. **Typewriter Effect:** Main landing page titles must use keyframe-driven character reveals or gradual opacity fade-ins to emulate conversational response times.
3. **Glow Pulse:** Actionable items (CTAs, latest status score) must feature a slow keyframe radial pulse:
   - `@keyframes pulseGlow { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }`

---

## 🤖 Agent Experience (AX) Integration

To optimize the interaction between the user and the sleep concierge agent:
1. **Generative UI Bubble Limits:** Rich components rendered in the chat panel must not exceed `320px` in width to avoid clipping the chat container.
2. **Contextual Suggesters:** Input suggestions must be dynamically updated using the hook `useCopilotChatSuggestions` with instructions reflecting current sleep scores.
3. **Coaching Visuals:** Tips returned by the agent must utilize matching category badge colors (e.g., caffeine tip matches warning colors, exercise matches success colors).
