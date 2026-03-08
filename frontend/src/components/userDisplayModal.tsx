"use client";

import { useState } from "react";
import pokeballImage from "frontend/public/light_grey_pokeball_by_jormxdos_dfgb85u-fullview.png";

function UserInfoModal() {
  const [isInfoDisplayed, setIsInfoDisplayed] = useState(false);

  return (
    <div className="user-info-modal">
      <button
        className="user-info-modal-button w-[50px] h-[50px] flex items-center justify-center"
        onClick={() => setIsInfoDisplayed(!isInfoDisplayed)}
      >
        <img
          className="w-[50px] h-[50px] hover:scale-110 transition-transform duration-200"
          src={pokeballImage.src}
        />
      </button>

      {isInfoDisplayed && (
        <div className="settings-modal">
          <p>Settings Menu Content</p>
        </div>
      )}
    </div>
  );
}

export default UserInfoModal;
