"use client";

import { useState } from "react";
import pokeballImage from "frontend/public/light_grey_pokeball_by_jormxdos_dfgb85u-fullview.png";

function UserInfoModal() {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isRotated, setIsRotated] = useState(false);

  const handleClick = () => {
    setIsModalOpen(!isModalOpen);
    setIsRotated(!isRotated);
  };

  const InfoDisplayPopUp = () => {
    return (
      <div className="fixed top-14 right-8 bg-white rounded-lg shadow-lg p-6 w-60 z-50">
        <div className="mt-4 text-black flex items-center justify-center">
          <h2>Settings Menu Content</h2>
        </div>
      </div>
    );
  };

  return (
    <div className="user-info-modal">
      <button
        className="user-info-modal-button w-[50px] h-[50px] flex items-center justify-center"
        onClick={handleClick}
      >
        <img
          className={`w-[50px] h-[50px] hover:scale-110 transition-transform duration-200 ${isRotated ? "rotate-180" : ""}`}
          src={pokeballImage.src}
        />
      </button>

      {isModalOpen && InfoDisplayPopUp()}
    </div>
  );
}

export default UserInfoModal;
