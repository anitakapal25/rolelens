import { useRef, useState, type DragEvent } from "react";

const ACCEPT = ".pdf,.docx,.txt";

interface Props {
  title: string;
  hint: string;
  multiple?: boolean;
  disabled?: boolean;
  onFiles: (files: File[]) => void;
}

export function Dropzone({ title, hint, multiple = false, disabled = false, onFiles }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const take = (list: FileList | null) => {
    if (!list || disabled) return;
    const files = Array.from(list);
    onFiles(multiple ? files : files.slice(0, 1));
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    take(e.dataTransfer.files);
  };

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={`flex w-full flex-col items-center justify-center rounded-xl border-2 border-dashed px-4 py-5 text-center transition
        ${over ? "border-accent-500 bg-accent-50" : "border-stone-300 bg-white hover:border-accent-500 hover:bg-accent-50/40"}
        disabled:cursor-not-allowed disabled:opacity-60`}
    >
      <span className="text-sm font-medium text-stone-800">{title}</span>
      <span className="mt-1 text-xs text-stone-500">{hint}</span>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple={multiple}
        className="hidden"
        onChange={(e) => {
          take(e.target.files);
          e.target.value = "";
        }}
      />
    </button>
  );
}
