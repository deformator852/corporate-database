/** A document an answer was built from. */
export type ChatSource = {
    id: number;
    name: string;
    filename: string;
};

export type AnswerRating = "up" | "down";
