# SIH26118 MRPL H₂S Dosimeter - Design System

## 1. Design Direction
**Technical, Professional, Dark, and Action-Oriented.**
The app serves as a critical safety and monitoring tool for industrial environments (MRPL Refineries). The UI emphasizes high contrast for visibility, data clarity, and an interface that feels like advanced scientific equipment. 

## 2. Color Palette (Dark Theme)
The application exclusively uses a specialized dark theme to reduce glare in industrial environments and highlight critical alerts.

### 2.1 Core Backgrounds & Surfaces
- **Background (`@color/h2s_bg`)**: `![#0A0E17](https://placehold.co/15x15/0A0E17/0A0E17.png) `#0A0E17`` — Main app background.
- **Surface (`@color/h2s_surface`)**: `![#111622](https://placehold.co/15x15/111622/111622.png) `#111622`` — Elevated areas like nav bars and bottom sheets.
- **Card (`@color/h2s_card`)**: `![#151D2A](https://placehold.co/15x15/151D2A/151D2A.png) `#151D2A`` — Default background for data cards and list items.
- **Elevated Card (`@color/h2s_card_elevated`)**: `![#1A2436](https://placehold.co/15x15/1A2436/1A2436.png) `#1A2436`` — Floating elements or active cards.
- **Strokes & Dividers**: 
  - Standard Stroke: `![#232E42](https://placehold.co/15x15/232E42/232E42.png) `#232E42`` (`h2s_card_stroke`)
  - Active Stroke: `![#354664](https://placehold.co/15x15/354664/354664.png) `#354664`` (`h2s_card_stroke_active`)
  - Divider: `![#1E293B](https://placehold.co/15x15/1E293B/1E293B.png) `#1E293B`` (`h2s_divider`)

### 2.2 Primary Accents (The "Blue" Identity)
- **Primary Blue (`@color/h2s_blue`)**: `![#2563EB](https://placehold.co/15x15/2563EB/2563EB.png) `#2563EB`` — Default buttons, active icons.
- **Dark Blue (`@color/h2s_blue_dark`)**: `![#1D4ED8](https://placehold.co/15x15/1D4ED8/1D4ED8.png) `#1D4ED8`` — Pressed button states.
- **Light Blue (`@color/h2s_blue_light`)**: `![#3B82F6](https://placehold.co/15x15/3B82F6/3B82F6.png) `#3B82F6`` — Highlights, progress bars, active nav items.
- **Cyan (`@color/h2s_cyan`)**: `![#06B6D4](https://placehold.co/15x15/06B6D4/06B6D4.png) `#06B6D4`` — Secondary technical accents.

### 2.3 Status & Alert Colors (Crucial for H₂S Monitoring)
- **Safe / Low / Normal (`h2s_green`)**: `![#10B981](https://placehold.co/15x15/10B981/10B981.png) `#10B981`` (Stroke: `![#059669](https://placehold.co/15x15/059669/059669.png) `#059669``, BG: `![#0E2820](https://placehold.co/15x15/0E2820/0E2820.png) `#0E2820``)
- **Elevated / Warning (`h2s_yellow`)**: `![#F59E0B](https://placehold.co/15x15/F59E0B/F59E0B.png) `#F59E0B`` (Stroke: `![#D97706](https://placehold.co/15x15/D97706/D97706.png) `#D97706``, BG: `![#291E0A](https://placehold.co/15x15/291E0A/291E0A.png) `#291E0A``)
- **High Danger (`h2s_orange`)**: `![#F97316](https://placehold.co/15x15/F97316/F97316.png) `#F97316`` (Stroke: `![#EA580C](https://placehold.co/15x15/EA580C/EA580C.png) `#EA580C``, BG: `![#31190B](https://placehold.co/15x15/31190B/31190B.png) `#31190B``)
- **Critical / Scan Failed (`h2s_red`)**: `![#EF4444](https://placehold.co/15x15/EF4444/EF4444.png) `#EF4444`` (Stroke: `![#DC2626](https://placehold.co/15x15/DC2626/DC2626.png) `#DC2626``, BG: `![#301416](https://placehold.co/15x15/301416/301416.png) `#301416``)

### 2.4 Typography Colors
- **White / Titles (`@color/h2s_text_white`)**: `![#FFFFFF](https://placehold.co/15x15/FFFFFF/FFFFFF.png) `#FFFFFF``
- **Primary Text (`@color/h2s_text_primary`)**: `![#F8FAFC](https://placehold.co/15x15/F8FAFC/F8FAFC.png) `#F8FAFC``
- **Secondary Text (`@color/h2s_text_secondary`)**: `![#94A3B8](https://placehold.co/15x15/94A3B8/94A3B8.png) `#94A3B8``
- **Muted Text (`@color/h2s_text_muted`)**: `![#64748B](https://placehold.co/15x15/64748B/64748B.png) `#64748B``
- **Dimmed Text (`@color/h2s_text_dim`)**: `![#475569](https://placehold.co/15x15/475569/475569.png) `#475569``

## 3. Typography & UI Elements
- **Font**: Inter (Clean, legible geometric sans-serif) or system default Roboto/San Francisco. 
- **Monospace Elements**: Use `fontFamily="monospace"` for technical readouts (e.g., PPM values, alignment status).
- **Corner Radii**: Use rounded corners for cards (`12dp` or `16dp`) to keep the interface friendly, but use precise layout grids.

## 4. Spacing System
Use an 8dp grid spacing system to ensure consistency:
- **Micro**: `4dp`, `8dp` (icon spacing, tight text rows)
- **Standard**: `16dp`, `20dp`, `24dp` (margins, card padding, layout gaps)
- **Macro**: `32dp`, `48dp`, `64dp` (section spacing, large padding)

## 5. Components
- **Buttons**: Use bold background colors (Primary Blue or Status colors) with fully rounded corners (`@drawable/bg_badge_blue` or similar) for primary actions. Use subtle surface backgrounds for secondary actions.
- **Data Cards**: Enclose related metrics (like Peak Intensity, Cumulative Dose) in `h2s_card` with `h2s_card_stroke` borders to keep them distinct.
- **Scanner Viewfinder**: Minimalist reticle (`h2s_reticle_corner`: `![#3B82F6](https://placehold.co/15x15/3B82F6/3B82F6.png) `#3B82F6``) with dark overlay (`![#05080E](https://placehold.co/15x15/05080E/05080E.png) `#05080E``) to focus the user's attention.

## 6. Development Best Practices
1. **Always use color resources**: Do not hardcode hex values like `![#FFFFFF](https://placehold.co/15x15/FFFFFF/FFFFFF.png) `#FFFFFF`` in layouts. Always use `@color/h2s_text_white`.
2. **Reusability**: Use styles or include existing layouts for repeated elements like the status chips (Safe/Critical).
3. **Responsive**: Ensure ConstraintLayouts are used for complex screens to automatically scale across various Android device aspect ratios (from small phones to large tablets).
