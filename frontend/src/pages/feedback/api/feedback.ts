import {api} from "@/shared/lib/api/client";
import {FEEDBACK_PER_PAGE, type RatedAnswerPage, type RatingFilter} from "@pages/feedback/model/feedback";

export async function getRatedAnswers(rating: RatingFilter, page: number): Promise<RatedAnswerPage> {
    const {data} = await api.get<RatedAnswerPage>("/chat/feedback", {
        params: {rating, page, per_page: FEEDBACK_PER_PAGE},
    });
    return data;
}

/** Takes a rated answer off the page (handled); the chat and the answer stay. */
export async function removeRating(messageId: number): Promise<void> {
    await api.delete(`/chat/feedback/${messageId}`);
}
