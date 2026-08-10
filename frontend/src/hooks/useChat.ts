import { useCallback, useEffect, useSyncExternalStore } from "react";
import { chatStore } from "../chat/store";

export function useChat() {
  const state = useSyncExternalStore(chatStore.subscribe, chatStore.snapshot);

  useEffect(() => {
    void chatStore.initialize();
  }, []);

  const sendMessage = useCallback((content: string) => chatStore.send(content), []);
  const cancelRun = useCallback(() => chatStore.cancel(), []);

  return { ...state, sendMessage, cancelRun };
}
