import {
  ClientSideRowModelModule,
  CustomFilterModule,
  ModuleRegistry,
  NumberFilterModule,
  TextFilterModule,
  colorSchemeDark,
  themeQuartz
} from 'ag-grid-community'

// Shared AG Grid setup for the list views. Every grid needs the same modules and
// the same theme, so it lives here instead of in each component.
//
// The client-side row model, the per-column text and number filters, and the
// custom multi-select value filter (the Set Filter itself is Enterprise).
ModuleRegistry.registerModules([ClientSideRowModelModule, TextFilterModule, NumberFilterModule, CustomFilterModule])

// The grid theme, mapped to the app's design tokens (styles.css :root) so the
// grid matches the rest of the SPA.
export const gridTheme = themeQuartz.withPart(colorSchemeDark).withParams({
  backgroundColor: 'var(--bg-1)',
  foregroundColor: 'var(--text)',
  accentColor: 'var(--accent)',
  borderColor: 'var(--border)',
  chromeBackgroundColor: 'var(--bg)',
  headerBackgroundColor: 'var(--bg)',
  headerTextColor: 'var(--muted)',
  dataBackgroundColor: 'var(--bg-1)',
  oddRowBackgroundColor: 'transparent',
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  fontSize: '13px',
  spacing: 6
})
