// src/components/Sidebar/SearchCard.tsx
import SearchIcon from '@/assets/svg/search.svg?react';
import { useState } from 'react';

type Props = {
  searchQuery: string;
  onSearch: (v: string) => void;
};

export default function SearchCard(props: Props) {
  const [value, setValue] = useState(props.searchQuery);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    setValue(next);

    // If cleared, immediately search empty
    if (next.trim() === '') {
      props.onSearch('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      props.onSearch(value);
    }
  };

  const handleClick = () => {
    props.onSearch(value);
  };

  return (
    <section className="card">
      <h2>Search</h2>
      <div className="search-row">
        <input
          type="text"
          className="search-input"
          placeholder="Search mail"
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
        />
        <button type="button" className="search-btn" aria-label="Search" onClick={handleClick}>
          <SearchIcon className="icon" aria-hidden />
        </button>
      </div>
    </section>
  );
}
