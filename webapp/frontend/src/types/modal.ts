// src/types/modal.ts
export type AppModalButtonVariant = "primary" | "secondary";

export type AppModalButton = {
  id: number;
  label: string;
  variant: AppModalButtonVariant;
  onClick: () => void;
};

export type AppModalState = {
  open: boolean;
  title: string;
  message: string;
  buttons: AppModalButton[];
};
