import React from "react";

export type AppModalButton = {
  id: number;
  label: string;
  variant?: "primary" | "secondary";
  onClick: () => void;
};

export type AppModalState = {
  open: boolean;
  title: string;
  message: string;
  buttons?: AppModalButton[];
};

export default function AppAlertModal(props: {
  state: AppModalState;
  onClose: () => void;
}) {
  const { state } = props;

  return (
    <div className={`app-modal-backdrop ${state.open ? "" : "hidden"}`} onMouseDown={props.onClose}>
      <div className="app-modal-dialog" onMouseDown={(e) => e.stopPropagation()}>
        <div className="app-modal-header">
          <h2 className="app-modal-title">{state.title}</h2>
        </div>
        <div className="app-modal-body">
          <p>{state.message}</p>
        </div>
        <div className="app-modal-footer">
          {(state.buttons?.length ? state.buttons : [{ id: 1, label: "OK", variant: "primary", onClick: props.onClose }]).map(
            (b) => (
              <button
                key={b.id}
                type="button"
                className={b.variant === "primary" ? "primary" : "secondary"}
                onClick={b.onClick}
              >
                {b.label}
              </button>
            )
          )}
        </div>
      </div>
    </div>
  );
}
