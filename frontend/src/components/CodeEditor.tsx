import { useEffect, useRef } from 'react'
import { EditorView, basicSetup } from 'codemirror'
import { keymap } from '@codemirror/view'
import { indentWithTab } from '@codemirror/commands'
import { HighlightStyle, indentUnit, syntaxHighlighting } from '@codemirror/language'
import { python } from '@codemirror/lang-python'
import { tags as t } from '@lezer/highlight'

export type EditorTheme = 'dark' | 'light'
type Props = { value: string; onChange: (value: string) => void; onRun?: () => void; label: string; readOnly?: boolean; theme?: EditorTheme }

// Dark navy theme in the spirit of DataCamp's script editor.
const darkTheme = EditorView.theme({
  '&': { color: '#e6edf5', backgroundColor: '#05192d' },
  '.cm-content': { caretColor: '#03ef62' },
  '.cm-cursor, .cm-dropCursor': { borderLeftColor: '#03ef62' },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': { backgroundColor: '#1f4a6e' },
  '.cm-gutters': { backgroundColor: '#05192d', color: '#7c8fa5', border: 'none' },
  '.cm-activeLine': { backgroundColor: '#0b2a47' },
  '.cm-activeLineGutter': { backgroundColor: '#0b2a47', color: '#e6edf5' },
  '.cm-matchingBracket': { backgroundColor: '#1f4a6e', outline: '1px solid #3f7cb0' },
  '.cm-tooltip': { backgroundColor: '#0b2a47', color: '#e6edf5', border: '1px solid #1f4a6e' },
  '.cm-tooltip-autocomplete > ul > li[aria-selected]': { backgroundColor: '#1f4a6e' },
  '.cm-panels': { backgroundColor: '#0b2a47', color: '#e6edf5' },
  '.cm-searchMatch': { backgroundColor: '#3a3a12' },
}, { dark: true })

const darkHighlight = HighlightStyle.define([
  { tag: t.comment, color: '#03ef62', fontStyle: 'italic' },
  { tag: [t.keyword, t.controlKeyword, t.operatorKeyword, t.definitionKeyword, t.moduleKeyword], color: '#ff6ea9' },
  { tag: [t.string, t.special(t.string)], color: '#ffc844' },
  { tag: [t.number, t.bool, t.null], color: '#ff931e' },
  { tag: [t.function(t.variableName), t.function(t.propertyName)], color: '#5eb1ff' },
  { tag: [t.definition(t.variableName), t.definition(t.function(t.variableName))], color: '#7dd3fc' },
  { tag: [t.className, t.typeName], color: '#c4a7ff' },
  { tag: t.standard(t.variableName), color: '#5eb1ff' },
  { tag: [t.operator, t.punctuation, t.bracket], color: '#cbd5e1' },
  { tag: t.propertyName, color: '#e6edf5' },
  { tag: t.variableName, color: '#e6edf5' },
])

// Python editor with line numbers, highlighting and auto-indent. Loaded lazily, so
// pages without code exercises do not download CodeMirror.
export default function CodeEditor({ value, onChange, onRun, label, readOnly = false, theme = 'dark' }: Props) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const handlers = useRef({ onChange, onRun, value })
  useEffect(() => { handlers.current = { onChange, onRun, value } }, [onChange, onRun, value])
  useEffect(() => {
    if (!host.current) return
    const editor = new EditorView({
      parent: host.current,
      doc: handlers.current.value,
      extensions: [
        basicSetup,
        python(),
        ...(theme === 'dark' ? [darkTheme, syntaxHighlighting(darkHighlight)] : []),
        indentUnit.of('    '),
        keymap.of([{ key: 'Mod-Enter', run: () => { handlers.current.onRun?.(); return true } }, indentWithTab]),
        EditorView.editable.of(!readOnly),
        EditorView.contentAttributes.of({ 'aria-label': label }),
        EditorView.updateListener.of(update => { if (update.docChanged) handlers.current.onChange(update.state.doc.toString()) }),
      ],
    })
    view.current = editor
    return () => { editor.destroy(); view.current = null }
  }, [readOnly, label, theme])
  useEffect(() => {
    const editor = view.current
    if (editor && editor.state.doc.toString() !== value) {
      editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: value } })
    }
  }, [value])
  return <div className={`code-editor-host code-editor-${theme}`} ref={host} />
}
