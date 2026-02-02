// src/components/Layout/Layout.tsx
import Sidebar, { type SidebarProps } from "./Sidebar";
import MiddleColumn, { type MiddleColumnProps } from "./MiddleColumn";
import DetailColumn, { type DetailColumnProps } from "./DetailColumn";

export default function Layout(props: {
  sidebar: SidebarProps;
  middle: MiddleColumnProps;
  detail: DetailColumnProps;
}) {
  return (
    <main className="layout">
      <aside className="sidebar">
        <Sidebar {...props.sidebar} />
      </aside>

      <section className="middle">
        <MiddleColumn {...props.middle} />
      </section>

      <section className="detail">
        <DetailColumn {...props.detail} />
      </section>
    </main>
  );
}
