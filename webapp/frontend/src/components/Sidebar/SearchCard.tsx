// src/components/Sidebar/SearchCard.tsx
import React from "react";
import searchIcon from "@/assets/svg/search.svg";

type Props = {
  searchQuery: string;
  onChange: (v: string) => void;
  onSearch: () => void;
};

export default function SearchCard(props: Props) {
  return (
    <section className="card">
      <h2>Search</h2>
      <div className="search-row">
        <input
          type="text"
          className="search-input"
          placeholder="Search mail"
          value={props.searchQuery}
          onChange={(e) => props.onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") props.onSearch();
          }}
        />
        <button type="button" className="search-btn" aria-label="Search" onClick={props.onSearch}>
          <img src={searchIcon} alt="" aria-hidden="true" className="icon-img" />
        </button>
      </div>
    </section>
  );
}