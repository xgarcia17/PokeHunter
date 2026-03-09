-- Generated from dataset_comp folder mapping + TCGdex set metadata
-- Source order preserved from: GET https://api.tcgdex.net/v2/en/sets

INSERT INTO sets (id, name, release_date)
VALUES
('base2', 'Jungle', '1999-06-16'),
('base3', 'Fossil', '1999-10-10'),
('si1', 'Southern Islands', '2001-07-31'),
('ecard1', 'Expedition Base Set', '2002-09-15'),
('bog', 'Best of game', '2002-12-01'),
('ecard2', 'Aquapolis', '2003-01-15'),
('ex1', 'Ruby & Sapphire', '2003-07-01'),
('ex2', 'Sandstorm', '2003-09-18'),
('ex6', 'FireRed & LeafGreen', '2004-09-01'),
('ex8', 'Deoxys', '2005-02-01'),
('ex9', 'Emerald', '2005-05-09'),
('ex11', 'Delta Species', '2005-10-31'),
('ex13', 'Holon Phantoms', '2006-05-03'),
('ex14', 'Crystal Guardians', '2006-08-30'),
('ex16', 'Power Keepers', '2007-02-17'),
('dp2', 'Mysterious Treasures', '2007-08-01'),
('dp3', 'Secret Wonders', '2007-11-01'),
('dp5', 'Majestic Dawn', '2008-05-01'),
('pl1', 'Platinum', '2009-02-11'),
('pl2', 'Rising Rivals', '2009-05-16'),
('pl4', 'Arceus', '2009-11-04'),
('ru1', 'Pokémon Rumble', '2009-12-02'),
('col1', 'Call of Legends', '2011-02-09'),
('bw2', 'Emerging Powers', '2011-08-31'),
('bw4', 'Next Destinies', '2012-02-08'),
('bw5', 'Dark Explorers', '2012-05-09'),
('bw7', 'Boundaries Crossed', '2012-11-07'),
('xy0', 'Kalos Starter Set', '2013-11-08'),
('xy2', 'Flashfire', '2014-05-07'),
('xy3', 'Furious Fists', '2014-08-13'),
('xy5', 'Primal Clash', '2015-02-04'),
('dc1', 'Double Crisis', '2015-03-25'),
('xy6', 'Roaring Skies', '2015-05-06'),
('xy7', 'Ancient Origins', '2015-08-12'),
('xy8', 'BREAKthrough', '2015-11-04'),
('xy9', 'BREAKpoint', '2016-02-03'),
('xy10', 'Fates Collide', '2016-05-02'),
('xy11', 'Steam Siege', '2016-08-03'),
('xy12', 'Evolutions', '2016-11-02'),
('sm3', 'Burning Shadows', '2017-08-04'),
('sm4', 'Crimson Invasion', '2017-11-03'),
('sm6', 'Forbidden Light', '2018-05-04'),
('sm7', 'Celestial Storm', '2018-08-03'),
('det1', 'Detective Pikachu', '2019-03-29'),
('swsh2', 'Rebel Clash', '2020-05-01'),
('swsh3', 'Darkness Ablaze', '2020-08-14'),
('fut2020', 'Pokémon Futsal 2020', '2020-09-11'),
('swsh3.5', 'Champion''s Path', '2020-09-25'),
('swsh6', 'Chilling Reign', '2021-06-18'),
('swsh7', 'Evolving Skies', '2021-08-27'),
('cel25', 'Celebrations', '2021-10-08'),
('swsh9', 'Brilliant Stars', '2022-02-25'),
('swsh10', 'Astral Radiance', '2022-05-27'),
('swsh12.5', 'Crown Zenith', '2023-01-20'),
('svp', 'SVP Black Star Promos', '2023-03-31'),
('sv01', 'Scarlet & Violet', '2023-03-31'),
('sv03.5', '151', '2023-09-22'),
('sv05', 'Temporal Forces', '2024-03-22'),
('sv07', 'Stellar Crown', '2024-09-13'),
('sv08.5', 'Prismatic Evolutions', '2025-01-17'),
('sv09', 'Journey Together', '2025-03-28'),
('sv10', 'Destined Rivals', '2025-05-30'),
('sv10.5b', 'Black Bolt', '2025-07-17'),
('me01', 'Mega Evolution', '2025-09-26'),
('mep', 'MEP Black Star Promos', '2025-09-26')
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  release_date = EXCLUDED.release_date;

-- Resolved sets: 65
-- Unresolved folders: 5
-- unresolved folder=box-topper raw_set_id=(none)
-- unresolved folder=hs-energy-2010-unnumbered raw_set_id=(none)
-- unresolved folder=mee raw_set_id=mee
-- unresolved folder=miscellaneous raw_set_id=(none)
-- unresolved folder=scarlet-violet-energy raw_set_id=sve
