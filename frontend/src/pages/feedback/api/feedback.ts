import {api} from "@/shared/lib/api/client";
import type {AnswerRating} from "@/entities/chat/model";
import {FEEDBACK_PER_PAGE, type RatedAnswerPage} from "@pages/feedback/model/feedback";

export async function getRatedAnswers(rating: AnswerRating, page: number): Promise<RatedAnswerPage> {
    const {data} = await api.get<RatedAnswerPage>("/chat/feedback", {
        params: {rating, page, per_page: FEEDBACK_PER_PAGE},
    });
    return data;
}
