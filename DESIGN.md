---
name: Inside the game — Conversational workspace
description: A monochrome workspace for asking, inspecting, and refining football analysis.
colors:
  dark-bg: "#181818"
  dark-side: "#131313"
  dark-panel: "#1c1c1c"
  dark-input: "#252525"
  dark-hover: "#2c2c2c"
  dark-line: "#363636"
  dark-text: "#ededed"
  dark-muted: "#adadad"
  dark-inverse: "#171717"
  dark-primary: "#e6e6e6"
  light-bg: "#f7f7f7"
  light-side: "#f0f0f0"
  light-panel: "#fdfdfd"
  light-input: "#ededed"
  light-hover: "#e5e5e5"
  light-line: "#d7d7d7"
  light-text: "#242424"
  light-muted: "#626262"
  light-inverse: "#fff"
  light-primary: "#292929"
typography:
  title:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 550
    lineHeight: 1.3
    letterSpacing: "-0.3px"
  body:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  message:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.5
  metadata:
    fontFamily: "Segoe UI, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  tag: "4px"
  control: "5px"
  action: "6px"
  identity: "7px"
  assistant: "8px"
  message: "10px"
spacing:
  tight: "4px"
  compact: "8px"
  control: "12px"
  panel: "16px"
  section: "20px"
  generous: "24px"
  message: "26px"
components:
  button-primary:
    backgroundColor: "{colors.dark-primary}"
    textColor: "{colors.dark-inverse}"
    rounded: "{rounded.action}"
    padding: "12px 18px"
    typography: "{typography.body}"
  button-primary-light:
    backgroundColor: "{colors.light-primary}"
    textColor: "{colors.light-inverse}"
    rounded: "{rounded.action}"
    padding: "12px 18px"
    typography: "{typography.body}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.control}"
    width: "32px"
    height: "32px"
  field:
    backgroundColor: "{colors.dark-input}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.action}"
    padding: "12px"
    typography: "{typography.body}"
  conversation-item:
    backgroundColor: "transparent"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.control}"
    padding: "10px 9px"
    typography: "{typography.body}"
  conversation-item-selected:
    backgroundColor: "{colors.dark-hover}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.control}"
    padding: "10px 9px"
    typography: "{typography.body}"
  agent-tag:
    backgroundColor: "transparent"
    textColor: "{colors.dark-muted}"
    rounded: "{rounded.tag}"
    padding: "2px 7px"
  user-message:
    backgroundColor: "{colors.dark-input}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.message}"
    padding: "12px 14px"
    typography: "{typography.message}"
  composer:
    backgroundColor: "{colors.dark-input}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.message}"
    padding: "11px 10px 40px"
  document-update:
    backgroundColor: "{colors.dark-panel}"
    textColor: "{colors.dark-text}"
    padding: "12px 16px"
  work-status:
    backgroundColor: "{colors.dark-input}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.assistant}"
    padding: "14px"
  panel-grip:
    backgroundColor: "{colors.dark-bg}"
    width: "8px"
---

# Design System: Inside the game — Conversational workspace

## Overview

**Creative North Star: "The Analysis Desk"**

The conversational workspace is a compact, quiet place to ask about a match,
inspect the resulting document, and continue refining it. Its visual language
comes from the implemented workspace: pure neutrals, tonal surfaces, restrained
dividers, compact controls, and visible keyboard focus. Black and white themes
carry equivalent roles.

This system applies to the conversational workspace and the match viewer.
`frontend/src/theme.css` owns their shared light/dark semantic roles, while
`frontend/src/hooks/use-theme.ts` persists one appearance preference across both
views and synchronises open tabs. Brand and theme controls are shared components.
The viewer uses the same neutral surfaces, typography, controls and dividers as
the workspace. Pitch, team and chart colours keep their analytical meanings;
the embedded report retains its theme adapter and original evidence.

**Key Characteristics:**
- Pure neutral interface with theme-paired semantic roles.
- Compact navigation and controls around a spacious document.
- Tonal grouping and fine dividers rather than raised cards.
- Geometric football imagery and inline outline SVG icons.
- Visible focus, real progress states, and reduced-motion support.
- Adjustable panes and explicit destinations for document updates.
- Readable analytical prose with visible provenance and scope.

## Colors

The shell uses grayscale exclusively; the document may retain its own analytical
colors. Every role maps to the matching `dark-*` or `light-*` frontmatter token.

### Primary
- **Action Ink / Action Paper:** `light-primary` and `dark-primary` provide the
  filled action background; their paired inverse tokens provide the text.

### Neutral
- **Workspace Ground:** `*-bg` is the central working surface.
- **Conversation Rail:** `*-side` separates history from the working area.
- **Assistant Surface:** `*-panel` anchors chat and the trace output.
- **Input Surface:** `*-input` groups editable fields, user messages, and notices.
- **Interaction Tone:** `*-hover` marks hover, selected conversations, and pressed
  document or mobile view controls.
- **Divider:** `*-line` separates panes, controls, and content rows.
- **Reading Ink:** `*-text` carries primary text and the focus outline.
- **Secondary Ink:** `*-muted` carries descriptions, labels, and provenance.

**The Paired Roles Rule.** Change themes by swapping the complete semantic role
set; keep the same information hierarchy in both themes.

**The Document Color Rule.** Keep the workspace shell monochrome while preserving
the report and viewer's established analytical color meanings.

## Typography

**Body Font:** Segoe UI, system-ui, sans-serif.

**Character:** Compact interface text supports a conversational tool. Hierarchy
comes from measured size and weight changes, muted metadata, and generous message
leading. These are interface roles, not a separate display identity.

### Hierarchy
- **Title:** the chat welcome heading uses the title token.
- **Body:** navigation, controls, and shell text use the body token.
- **Message:** chat paragraphs use the message token and preserve line breaks.
- **Label:** pane headings use the label token.
- **Metadata:** supporting row descriptions and toolbar actions use the metadata
  size; source notes and the agent badge are smaller local treatments (10px).

Large empty-state and login headings are existing surface-specific treatments;
they are not canonized as a reusable system display face. Trace JSON uses the
browser's monospace default at 11px with 1.6 line height.

## Layout

The desktop workspace fills `100dvh`. The default arrangement is conversations
on the left, a flexible document in the center, and chat on the right. Chat can
move to the other side of the document. Initial widths are 220px for history and
350px for chat; layout preferences persist locally. Above 900px, history can
collapse to a 62px icon rail. Reset restores initial widths, expanded history,
and chat on the right.

History resizes between 170px and 300px; chat resizes between 250px and 620px,
with tighter maxima when space is limited. Chat's clamp preserves 290px in its
container; history's clamp reserves 700px of viewport width. A 6px history grip
and 8px chat grip provide separate drag targets. Keyboard separators expose
their current range and value: arrows change 10px, Shift plus arrows 40px, and
Home/End select the allowed extremes. Double-click restores that panel's default,
subject to the same clamp. While dragging, the iframe stops intercepting pointers.

Between 761px and 900px, history uses the 62px icon strip and its resizing/collapse
controls are hidden; chat remains adjustable. At 760px and below, conversations
move into a 240px modal drawer and the top bar becomes 54px. Resize and docking
controls are hidden. Document and chat alternate through explicit view buttons;
the active pane takes the available height. The desktop top bar is 62px, and
document toolbar and chat heading are 52px. Panes scroll independently, with the
composer anchored below messages.

The spacing scale is a vocabulary of repeated values, not a strict multiple-only
grid. Conversation rows have a compact 4px gap, panel padding commonly uses 16px,
20px, or 24px, and messages separate by 26px. Starting-point rows share a maximum
400px width. The login content is at most 420px; chat welcome content is capped
at 340px on mobile. Long titles truncate; message and trace text wrap.

## Elevation & Depth

Depth comes from tonal planes and single-pixel dividers. Desktop surfaces have
no shadows. The mobile conversation drawer alone gains a diffuse edge shadow
(`20px 0 45px #0004`) when open. It is a modal layer with focus containment,
Escape and close actions, focus restoration, and inert background content.

**The Flat Workspace Rule.** Keep permanent desktop panes flat; reserve the
implemented shadow for the temporary mobile drawer.

## Shapes

Small rounded corners soften compact controls: tag, control, action, identity,
and assistant radii form the smaller scale; user bubbles and the composer use
the message radius. Pane boundaries remain square. Fields and outline actions
use a single-pixel divider-colored border. The football illustration is sparse
line geometry with filled player dots and dashed connections; it is inline SVG,
not a raster asset.

## Components

### Buttons
Filled actions use primary and inverse roles with the action radius. Icon
buttons are transparent 32px squares with the control radius. Outline new-analysis
actions use a divider-colored border, the identity radius, and 10px 12px padding.
Ghost hover uses the interaction tone. Filled action hover preserves its paired
colors and applies `brightness(0.88)`. Disabled buttons use opacity 0.4.

Keyboard focus uses a 2px reading-ink outline with a 3px offset on buttons,
links, inputs, selects, and textareas. Background and color changes last 0.15s.

### Chips
The interpreter badge is descriptive metadata, not a filter: muted text, a fine
divider-colored border, the tag radius, and 10px type. It has no selected state.

### Cards / Containers
The workspace uses structural panes rather than a repeated raised-card system.
The user message is the recurring compact container: input surface, message
radius, 12px 14px padding, and a 24px left inset. Assistant messages remain on
the chat surface with a small speaker label and preserved text breaks.
Assistant replies can explain a concept without creating a document. Following
an analysis, their open-text treatment carries a short answer from validated
analytical statements, rather than replacing the answer with a graphic count.
The frontend preserves that server-authored answer even when its scope is partial.
The bounded progress panel is a functional state container: input surface,
assistant radius, fine divider border, and 14px padding. It does not change the
flat-pane rule.

### Inputs / Fields
Login fields use the input surface, action radius, and divider border. The match
selector is a compact panel-colored field with the control radius and 11px type.
The composer uses the message radius and reserves its bottom area for the 29px
send action. Its textarea has 58px minimum and 180px maximum height and resizes
vertically. Placeholder text is muted. The visible source label follows match
selection, including explicit synthetic-data identification.

### Navigation
Conversation rows are left-aligned, single-line entries with an outline SVG icon,
ellipsis truncation, and the same interaction tone for hover and selection.
Theme switching sits above the session footer. The narrow rail hides text
visually while retaining accessible labels. Mobile uses a labeled drawer and
pressed-state document/chat controls.

### Starting points and progress
Starting points form a divided list with an action title, muted description,
and a trailing arrow; they do not become separate cards. In-flight work appears
both above the document and in chat: real stage text, elapsed seconds with
tabular numerals, and a 14px spinner. Chat groups stages into Intención, Datos,
and Informe without inventing completion percentages. After 25 seconds the
supporting copy reassures that the current document remains available; it makes
no delivery-time promise. The original small dot remains for history/empty-state
progress. Reading older chat messages does not force a jump to the bottom;
a Nuevos mensajes control offers a return.

### Document updates and recovery
After a requested publication or newer revision, a flat notice reports counts
of added, updated, and removed graphics, or a title/analysis-only change. It
shows the revision and an explicit Ver cambios action; the report also offers
Ir a los gráficos and Leer análisis. New or changed blocks receive an Actualizado
label. Navigation moves focus and scroll to the intended content through a
token-bearing message bridge inside the isolated iframe. The document keeps its
separate analytical visual system.
Its existing script hashes remain in force; an ephemeral nonce authorizes the
injected bridge. Document navigation becomes available after the embedded DOM
confirms readiness through a message whose source and token the parent verifies.

The embedded analytical reading uses section headings and readable paragraphs.
Provenance and the first limitation stay visible; remaining scope detail and
sources use labeled disclosures. Statement kinds, facts, and citations remain
in the underlying analytical contract and trace. These are report presentation
patterns and do not introduce a new workspace palette or typography system.

Failures use plain recovery copy, with technical details behind a disclosure.
Reintentar solicitud or Completar análisis appears only when applicable. A partial
analysis with no issues and complete graphics retains the validated answer and
its limited-scope wording, rather than being treated as a failed or exhaustive
analysis. Failed refreshes
keep the previously displayed document available.

### Motion
Controls use the 150ms feedback duration and `cubic-bezier(0.23, 1, 0.32, 1)`
for the implemented press response; primary/send/retry actions scale to 0.96
while pressed. Chat docking uses a 200ms position animation with that easing.
The spinner rotates over 1s, the small dot pulses over 1.5s, and the drawer moves
over 0.2s. Reduced-motion disables spinners, docking motion, press scaling, and
ordinary transitions; the update notice permits only a 100ms opacity transition.

## Do's and Don'ts

### Do:
- **Do** apply the complete theme role set and keep focus visible in both modes.
- **Do** preserve independent pane scrolling and keep chat composition reachable.
- **Do** show evidence provenance, including synthetic-data labels, near selection.
- **Do** use inline outline SVG icons and geometric football illustrations.
- **Do** preserve the existing report and topology viewer's analytical colors.
- **Do** pair update summaries with a destination and keep old evidence readable
  while the next version is being prepared.
- **Do** keep provenance and the first limitation visible when source details
  are folded behind disclosures in the report.

### Don't:
- **Don't** introduce a chromatic accent into the monochrome workspace shell.
- **Don't** turn flat workspace panes into a collection of raised cards.
- **Don't** reuse the mobile drawer shadow on permanent desktop surfaces.
- **Don't** promote surface-specific large headings or the existing text-glyph
  error dismiss control into reusable display or icon primitives.
- **Don't** substitute an elapsed timer or ready graphics for a promise of
  exhaustive analysis or a fixed completion time.
