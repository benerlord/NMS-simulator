import Editor from '@monaco-editor/react';

interface Props {
  value: string;
  onChange: (v: string) => void;
  language?: string;
  height?: number;
}

const MonacoField = ({ value, onChange, language = 'json', height = 200 }: Props) => (
  <div style={{ border: '1px solid #d9d9d9', borderRadius: 6 }}>
    <Editor
      height={height}
      language={language}
      value={value}
      onChange={(v) => onChange(v || '')}
      options={{
        minimap: { enabled: false },
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        fontSize: 13,
        tabSize: 2,
        wordWrap: 'on',
        automaticLayout: true,
      }}
    />
  </div>
);

export default MonacoField;
