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

  const fakeUser = {
    id: "FranzK2026",
    name: "Franz the Trainer",
  };

  const InfoDisplayPopUp = () => {
    return (
      <div className="fixed top-14 right-8 bg-purple-200 rounded-lg shadow-lg p-1 w-60 z-50 border border-gray-300">
        {/* Inner outlined box */}
        <div className="w-full flex items-center justify-center rounded-md px-3 py-2 text-black bg-white">
          <h2 className="font-semibold">{fakeUser.name}</h2>
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
