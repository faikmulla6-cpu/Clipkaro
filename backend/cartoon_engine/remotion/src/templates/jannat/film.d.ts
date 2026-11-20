export type JannatFilmOptions = {
  durationSeconds?: number;
};

export function renderFilm(
  seconds: number,
  episodeLipEnvelope?: number[],
  options?: JannatFilmOptions,
): string;
