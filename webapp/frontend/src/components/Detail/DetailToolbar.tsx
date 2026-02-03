import ArchiveIcon from '@/assets/svg/box-archive.svg?react';
import DeleteIcon from '@/assets/svg/delete.svg?react';
import ReplyIcon from '@/assets/svg/reply.svg?react';
import ReplyAllIcon from '@/assets/svg/reply-all.svg?react';
import ForwardIcon from '@/assets/svg/forward.svg?react';
import FolderIcon from '@/assets/svg/folder.svg?react';

export type DetailToolbarProps = {
  onArchive: () => void;
  onDelete: () => void;
  onReply: () => void;
  onReplyAll: () => void;
  onForward: () => void;
  onToggleMove: () => void;
};

export default function DetailToolbar(props: DetailToolbarProps) {
  return (
    <div className="detail-toolbar">
      <button
        type="button"
        className="icon-btn"
        title="Archive"
        aria-label="Archive"
        onClick={props.onArchive}
      >
        <ArchiveIcon className="icon" aria-hidden />
      </button>

      <button
        type="button"
        className="icon-btn"
        title="Delete"
        aria-label="Delete"
        onClick={props.onDelete}
      >
        <DeleteIcon className="icon" aria-hidden />
      </button>

      <span className="toolbar-separator" />

      <button
        type="button"
        className="icon-btn"
        title="Reply"
        aria-label="Reply"
        onClick={props.onReply}
      >
        <ReplyIcon className="icon" aria-hidden />
      </button>

      <button
        type="button"
        className="icon-btn"
        title="Reply all"
        aria-label="Reply all"
        onClick={props.onReplyAll}
      >
        <ReplyAllIcon className="icon" aria-hidden />
      </button>

      <button
        type="button"
        className="icon-btn"
        title="Forward"
        aria-label="Forward"
        onClick={props.onForward}
      >
        <ForwardIcon className="icon" aria-hidden />
      </button>

      <span className="toolbar-spacer" />

      <button
        type="button"
        className="icon-btn"
        title="Move"
        aria-label="Move"
        onClick={props.onToggleMove}
      >
        <FolderIcon className="icon" aria-hidden />
      </button>
    </div>
  );
}
