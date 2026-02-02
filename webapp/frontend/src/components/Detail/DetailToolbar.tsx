
import archiveIcon from "@/assets/svg/box-archive.svg";
import deleteIcon from "@/assets/svg/delete.svg";
import replyIcon from "@/assets/svg/reply.svg";
import replyAllIcon from "@/assets/svg/reply-all.svg";
import forwardIcon from "@/assets/svg/forward.svg";
import folderIcon from "@/assets/svg/folder.svg";

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
      <button type="button" className="icon-btn" title="Archive" aria-label="Archive" onClick={props.onArchive}>
        <img src={archiveIcon} alt="" aria-hidden="true" className="icon-img" />
      </button>

      <button type="button" className="icon-btn" title="Delete" aria-label="Delete" onClick={props.onDelete}>
        <img src={deleteIcon} alt="" aria-hidden="true" className="icon-img" />
      </button>

      <span className="toolbar-separator" />

      <button type="button" className="icon-btn" title="Reply" aria-label="Reply" onClick={props.onReply}>
        <img src={replyIcon} alt="" aria-hidden="true" className="icon-img" />
      </button>

      <button type="button" className="icon-btn" title="Reply all" aria-label="Reply all" onClick={props.onReplyAll}>
        <img src={replyAllIcon} alt="" aria-hidden="true" className="icon-img" />
      </button>

      <button type="button" className="icon-btn" title="Forward" aria-label="Forward" onClick={props.onForward}>
        <img src={forwardIcon} alt="" aria-hidden="true" className="icon-img" />
      </button>

      <span className="toolbar-spacer" />

      <button type="button" className="icon-btn" title="Move" aria-label="Move" onClick={props.onToggleMove}>
        <img src={folderIcon} alt="" aria-hidden="true" className="icon-img" />
      </button>
    </div>
  );
}
