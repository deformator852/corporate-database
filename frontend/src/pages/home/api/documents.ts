import {api} from "@/shared/lib/api/client";
import type {ChatDocument} from "@pages/home/model/chat";

type DocumentPage = {items: ChatDocument[]; page: number; pages: number};

/** Processed documents the user may ask about, for the document picker. */
export async function getReadyDocumentsPage(page: number, perPage: number, query: string) {
    const {data} = await api.get<DocumentPage>("/documents", {
        params: {page, per_page: perPage, q: query || undefined, status: "completed"},
    });
    return {
        page: data.page,
        pages: data.pages,
        items: data.items.map(({id, name}) => ({key: String(id), id, name})),
    };
}
